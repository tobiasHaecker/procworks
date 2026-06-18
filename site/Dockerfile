FROM caddy:2-alpine

# Sicherheits-Updates der Basis-Distribution einspielen
RUN apk --no-cache -U upgrade

COPY index.html styles.css /srv/
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
