{{- define "ai-gateway.labels" -}}
app.kubernetes.io/name: ai-gateway
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
