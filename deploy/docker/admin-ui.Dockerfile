# Vue admin UI: build static assets, serve via nginx (proxies /api to control plane).
FROM node:20-slim AS build
WORKDIR /ui
COPY admin-ui/package.json admin-ui/package-lock.json* ./
RUN npm ci || npm install
COPY admin-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
