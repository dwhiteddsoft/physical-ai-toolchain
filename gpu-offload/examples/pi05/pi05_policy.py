# SPDX-License-Identifier: MIT
#
# Pi0.5 policy wrapper for the GPU offload boundary.
#
# Adapted from Physical-AI-Operator `physical_ai_operator/policies/lerobot_policy.py`
# (lerobot 0.4.3 API) and reduced to a plain-type interface so the calls can cross the
# remoter wire.
#
# Why this wrapper instead of remoting `lerobot.policies.pi05.modeling_pi05/PI05Policy`
# directly:
#
#   * lerobot resolves the concrete policy class through `get_policy_class(cfg.type)`,
#     so the object the control loop holds does not come from a module attribute the
#     remoter can decorate.
#   * `select_action` takes and returns torch tensors, and the MessagePack codec
#     rejects tensors. Normalization, tokenization, and un-normalization must all stay
#     on the GPU side of the boundary.
#
# Every method here therefore exchanges only str, int, float, bytes, list, and dict.
# torch, lerobot, and numpy are imported inside the methods: the client container
# imports this module to install the remoter decorators and must not need CUDA.
from __future__ import annotations

import os

# cspell:ignore frombuffer imdecode imencode IMREAD

CAMERA_KEY_FORMAT = "observation.images.{name}"
STATE_KEY = "observation.state"


class Pi05Policy:
    """Pi0.5 checkpoint executed in the GPU server stage.

    Args:
        pretrained_path: Checkpoint directory holding `config.json`, `model.safetensors`,
            and the saved pre/post-processor pipelines.
        device: Torch device string used for the weights and the inference pass.
        fps: Control-loop rate. pi05 emits a chunk of absolute joint targets meant to be
            replayed at the training fps; this checkpoint was trained at 15 Hz.
        task: Default language instruction. pi05 is language-conditioned and drifts
            off-distribution when the prompt differs from the training string.
    """

    def __init__(
        self,
        pretrained_path: str,
        device: str = "cuda",
        fps: int = 15,
        task: str = "",
    ) -> None:
        self.pretrained_path = pretrained_path
        self.device = device
        self.fps = int(fps)
        self.task = task
        self._loaded = False

    def load(self) -> dict[str, object]:
        """Load the checkpoint and its processors, then run one warmup pass.

        Declared `singleinstance: true` so the 7 GB of weights load once per server
        stage and every control cycle reuses them. Returns provenance the caller can
        log to confirm which pod executed the load.
        """
        import torch
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.policies.factory import get_policy_class, make_pre_post_processors

        os.environ.setdefault("HF_HUB_OFFLINE", "1")

        config = PreTrainedConfig.from_pretrained(self.pretrained_path)
        config.pretrained_path = self.pretrained_path
        config.device = self.device

        # pi05 checkpoints ship compile_model=True. Compilation makes the first load
        # take minutes and can wedge startup, and deterministic startup matters more
        # than compile-time throughput for on-robot playback.
        if getattr(config, "compile_model", False):
            config.compile_model = False

        policy_class = get_policy_class(config.type)
        self._policy = policy_class.from_pretrained(self.pretrained_path, config=config).to(self.device).eval()

        # The saved pipelines carry the QUANTILE state/action normalization, the camera
        # key rename, and the PaliGemma tokenizer. Skipping them produces garbage actions.
        self._preprocessor, self._postprocessor = make_pre_post_processors(
            policy_cfg=config,
            pretrained_path=self.pretrained_path,
            preprocessor_overrides={"device_processor": {"device": self.device}},
        )
        self._loaded = True

        return {
            "executed_by": os.environ.get("HOSTNAME", "unknown"),
            "policy_class": policy_class.__name__,
            "policy_type": str(config.type),
            "device": self.device,
            "torch_version": str(torch.__version__),
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_name": str(torch.cuda.get_device_name(0)) if torch.cuda.is_available() else "",
        }

    def reset(self) -> None:
        """Drop the queued action chunk so the next call starts a fresh episode."""
        if not self._loaded:
            return
        for target in (self._policy, self._preprocessor, self._postprocessor):
            if hasattr(target, "reset"):
                target.reset()

    def select_action(
        self,
        state: list[float],
        frames: dict[str, bytes],
        task: str = "",
    ) -> list[float]:
        """Predict one action for a single observation.

        Args:
            state: Joint positions plus gripper in physical units, ordered as during training.
            frames: JPEG-encoded RGB frames keyed by the training camera name.
            task: Language instruction; falls back to the instruction given at
                construction time.

        Returns:
            The action vector in physical units as plain floats.
        """
        import cv2
        import numpy as np
        import torch
        from lerobot.utils.control_utils import predict_action

        if not self._loaded:
            self.load()

        observation: dict[str, object] = {STATE_KEY: np.asarray(state, dtype=np.float32)}
        for name, jpeg in frames.items():
            buffer = np.frombuffer(jpeg, dtype=np.uint8)
            image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"camera {name} sent a frame that is not decodable JPEG")
            observation[CAMERA_KEY_FORMAT.format(name=name)] = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        action = predict_action(
            observation,
            self._policy,
            torch.device(self.device),
            self._preprocessor,
            self._postprocessor,
            use_amp=False,
            task=task or self.task or None,
        )
        return [float(value) for value in action.detach().to("cpu").numpy().flatten()]
