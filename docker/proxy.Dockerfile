ARG METIER_IMAGE=intern-metier:etape12
FROM ${METIER_IMAGE} AS statiques
RUN .venv/bin/python app/manage.py collectstatic --noinput --skip-checks

FROM node:22.23.3-alpine3.23 AS client
WORKDIR /client
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund && npm cache clean --force
COPY frontend/ ./
ENV VITE_API_ROOT=/api/v1
RUN npm run build

FROM nginx:1.28.0-alpine
COPY docker/proxy.conf /etc/nginx/conf.d/default.conf
COPY --from=client /client/dist /usr/share/nginx/html
COPY --from=statiques /app/staticfiles /usr/share/nginx/static
