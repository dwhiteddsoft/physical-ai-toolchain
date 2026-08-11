{{- $repository := .Values.image.repository -}}
{{- if .Values.image.registry -}}
{{- $repository = printf "%s/%s" (trimSuffix "/" .Values.image.registry) $repository -}}
{{- end -}}
{{- $image := printf "%s:%s" $repository .Values.image.tag -}}
{{- if .Values.image.digest -}}
{{- $image = printf "%s@%s" $repository .Values.image.digest -}}
{{- end -}}
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
apiVersion: v1
kind: ConfigMap
metadata:
  name: first-run-offload
  namespace: {{ .Release.Namespace }}
data:
  remote.yaml: |
    serverstages:
      - name: {{ .Values.serverStage.name }}
        perclient: false
        serverimage: {{ $image | quote }}
{{- if .Values.serverStage.wslNvidia.enabled }}
        env:
          - name: LD_LIBRARY_PATH
            value: {{ .Values.serverStage.wslNvidia.driverLibraryPath | quote }}
{{- end }}
        resources:
          requests:
{{ toYaml .Values.serverStage.resources.requests | indent 12 }}
          limits:
{{- range $key, $value := .Values.serverStage.resources.limits }}
            {{ $key }}: {{ $value | quote }}
{{- end }}
{{- if .Values.serverStage.wslNvidia.enabled }}
            {{ .Values.serverStage.wslNvidia.resourceName }}: {{ .Values.serverStage.wslNvidia.quantity | quote }}
{{- end }}
    remotefuncs:
      - "demo_model//predict":
          remoteloc: {{ .Values.serverStage.name }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: first-run-client
  namespace: {{ .Release.Namespace }}
  labels:
    app: first-run-client
    xavier: "true"
  annotations:
    xavierconfig: |
      remoteablecm: first-run-offload
      remoteableconts:
        - client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: first-run-client
  template:
    metadata:
      labels:
        app: first-run-client
        xavier: "true"
    spec:
      serviceAccountName: gpu-offload-runtime
      containers:
        - name: client
          image: {{ $image | quote }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          env:
            - name: REMOTERPORT
              value: "30001"
          resources:
{{ toYaml .Values.clientResources | indent 12 }}
