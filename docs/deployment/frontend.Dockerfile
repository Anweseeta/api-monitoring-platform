# Frontend image (React + Vite).
# Copy to frontend/Dockerfile to build standalone:
#   cp docs/deployment/frontend.Dockerfile frontend/Dockerfile
#
# Build-time arg: VITE_API_URL must be baked in at build time
# (Vite embeds VITE_* vars into the bundle).
FROM node:24-alpine AS build

WORKDIR /app
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Serve the static bundle with nginx (SPA fallback to index.html).
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
