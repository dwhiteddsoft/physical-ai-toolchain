{{- $registry := trimSuffix "/" .Values.image.registry -}}
{{- $repository := .Values.image.repository -}}
{{- if $registry -}}
{{- $repository = printf "%s/%s" $registry $repository -}}
{{- end -}}
{{- $image := printf "%s:%s" $repository .Values.image.tag -}}
{{- if .Values.image.digest -}}
{{- $image = printf "%s@%s" $repository .Values.image.digest -}}
{{- end -}}
{{- $serverRepository := .Values.image.repository -}}
{{- if .Values.serverStage.image.repository -}}
{{- $serverRepository = .Values.serverStage.image.repository -}}
{{- end -}}
{{- if $registry -}}
{{- $serverRepository = printf "%s/%s" $registry $serverRepository -}}
{{- end -}}
{{- $serverTag := .Values.image.tag -}}
{{- if .Values.serverStage.image.tag -}}
{{- $serverTag = .Values.serverStage.image.tag -}}
{{- end -}}
{{- $serverImage := printf "%s:%s" $serverRepository $serverTag -}}
{{- $modelPath := required "model.hostPath must point at the pi05 checkpoint directory on the node" .Values.model.hostPath -}}
{{- $cachePath := required "huggingFaceCache.hostPath must point at the HuggingFace cache on the node" .Values.huggingFaceCache.hostPath -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gpu-offload-runtime
  namespace: {{ .Release.Namespace }}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
{{ toYaml . | indent 2 }}
{{- end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: gpu-offload-runtime
  namespace: {{ .Release.Namespace }}
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: gpu-offload-runtime
  namespace: {{ .Release.Namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: gpu-offload-runtime
subjects:
  - kind: ServiceAccount
    name: gpu-offload-runtime
    namespace: {{ .Release.Namespace }}
---
# The checkpoint stays on the node. A hostPath PersistentVolume is the only way to
# expose it to the generated server pod: controller/mutate.py copies configMap,
# downwardAPI, emptyDir, ephemeral, persistentVolumeClaim, projected, and secret
# volumes from the client, and explicitly rejects raw hostPath volumes.
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {{ .Release.Name }}-model
  labels:
    app: {{ .Release.Name }}
spec:
  capacity:
    storage: {{ .Values.model.capacity }}
  accessModes:
    - ReadOnlyMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  claimRef:
    name: {{ .Release.Name }}-model
    namespace: {{ .Release.Namespace }}
  hostPath:
    path: {{ $modelPath | quote }}
    type: Directory
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ .Release.Name }}-model
  namespace: {{ .Release.Namespace }}
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: ""
  volumeName: {{ .Release.Name }}-model
  resources:
    requests:
      storage: {{ .Values.model.capacity }}
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {{ .Release.Name }}-hf-cache
  labels:
    app: {{ .Release.Name }}
spec:
  capacity:
    storage: {{ .Values.huggingFaceCache.capacity }}
  accessModes:
    - ReadOnlyMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  claimRef:
    name: {{ .Release.Name }}-hf-cache
    namespace: {{ .Release.Namespace }}
  hostPath:
    path: {{ $cachePath | quote }}
    type: Directory
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ .Release.Name }}-hf-cache
  namespace: {{ .Release.Namespace }}
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: ""
  volumeName: {{ .Release.Name }}-hf-cache
  resources:
    requests:
      storage: {{ .Values.huggingFaceCache.capacity }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Release.Name }}-offload
  namespace: {{ .Release.Namespace }}
data:
  # Keep in sync with ../remote.yaml.
  remote.yaml: |
    serverstages:
      - name: {{ .Values.serverStage.name }}
        perclient: false
        serverimage: {{ $serverImage | quote }}
        resources:
          requests:
{{ toYaml .Values.serverStage.resources.requests | indent 12 }}
          limits:
{{- range $key, $value := .Values.serverStage.resources.limits }}
            {{ $key }}: {{ $value | quote }}
{{- end }}
            {{ .Values.serverStage.gpu.resourceName }}: {{ .Values.serverStage.gpu.quantity | quote }}
    remoteclasses:
      - "pi05_policy/Pi05Policy":
          remoteloc: {{ .Values.serverStage.name }}
    remotefuncs:
      # load pulls roughly 7 GB of weights onto the GPU; singleinstance keeps one
      # loaded policy per stage so every control cycle reuses it.
      - "pi05_policy/Pi05Policy/load":
          singleinstance: true
          remoteloc: {{ .Values.serverStage.name }}
      - "pi05_policy/Pi05Policy/reset":
          singleinstance: true
          remoteloc: {{ .Values.serverStage.name }}
      - "pi05_policy/Pi05Policy/select_action":
          singleinstance: true
          remoteloc: {{ .Values.serverStage.name }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-control
  namespace: {{ .Release.Namespace }}
  labels:
    app: {{ .Release.Name }}-control
    xavier: "true"
  annotations:
    xavierconfig: |
      remoteablecm: {{ .Release.Name }}-offload
      remoteableconts:
        - control
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {{ .Release.Name }}-control
  template:
    metadata:
      labels:
        app: {{ .Release.Name }}-control
        xavier: "true"
    spec:
      serviceAccountName: gpu-offload-runtime
{{- with .Values.nodeSelector }}
      nodeSelector:
{{ toYaml . | indent 8 }}
{{- end }}
      volumes:
        - name: pi05-model
          persistentVolumeClaim:
            claimName: {{ .Release.Name }}-model
            readOnly: true
        - name: pi05-hf-cache
          persistentVolumeClaim:
            claimName: {{ .Release.Name }}-hf-cache
            readOnly: true
      containers:
        - name: control
          image: {{ $image | quote }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          # The control container never reads either volume. It declares the mounts so
          # the controller propagates them to the generated server pod, which is where
          # the weights and the tokenizer are loaded.
          volumeMounts:
            - name: pi05-model
              mountPath: {{ .Values.model.mountPath }}
              readOnly: true
            - name: pi05-hf-cache
              mountPath: {{ .Values.huggingFaceCache.mountPath }}
              readOnly: true
          env:
            - name: REMOTERPORT
              value: "30001"
            # Env declared here is merged into the generated server container, so the
            # GPU stage resolves the same checkpoint path and tokenizer cache.
            - name: PI05_MODEL_PATH
              value: {{ .Values.model.mountPath | quote }}
            - name: HF_HOME
              value: {{ .Values.huggingFaceCache.mountPath | quote }}
            - name: HF_HUB_OFFLINE
              value: "1"
            - name: PI05_TASK
              value: {{ .Values.policy.task | quote }}
            - name: PI05_FPS
              value: {{ .Values.policy.fps | quote }}
            - name: PI05_CAMERAS
              value: {{ .Values.policy.cameras | quote }}
            - name: PI05_DRY_RUN
              value: {{ .Values.policy.dryRun | quote }}
            - name: PI05_ENABLE_MOTION
              value: {{ .Values.policy.enableMotion | quote }}
          resources:
{{ toYaml .Values.clientResources | indent 12 }}
