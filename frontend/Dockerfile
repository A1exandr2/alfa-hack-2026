FROM nginx:1.28.0-alpine3.21
COPY devops/nginx.conf /etc/nginx/nginx.conf
COPY frontend/index.html frontend/styles.css frontend/app.js /usr/share/nginx/html/
COPY frontend/assets /usr/share/nginx/html/assets
EXPOSE 8080
