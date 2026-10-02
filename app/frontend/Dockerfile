FROM nginxinc/nginx-unprivileged:1.31.6-alpine3.24@sha256:26b0bf6fbf07297983cb341998d79c831508787de26627dd2a112321b9c3a4af

ARG VERSION=dev
ARG REVISION=unknown
ARG SOURCE=https://github.com/MyoMyatMin/k8slab

LABEL org.opencontainers.image.title="k8slab-frontend" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${REVISION}" \
    org.opencontainers.image.source="${SOURCE}"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js styles.css  /usr/share/nginx/html/

USER 101:101
EXPOSE 8080
