# Dev-mode image: source is bind-mounted over /app at runtime for hot reload
# (see ../docker-compose.yml); node_modules stays in an anonymous volume so
# the bind mount doesn't shadow it with the host's (possibly wrong-platform)
# node_modules.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
