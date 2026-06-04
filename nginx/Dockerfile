FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf && \
    mkdir -p /var/cache/nginx/cards && \
    chown -R nginx:nginx /var/cache/nginx
COPY nginx.conf /etc/nginx/conf.d