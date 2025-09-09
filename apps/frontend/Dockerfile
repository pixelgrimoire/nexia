FROM node:20-bullseye
WORKDIR /app
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./
RUN if [ -f pnpm-lock.yaml ]; then npm i -g pnpm && pnpm i; \
	elif [ -f yarn.lock ]; then yarn; \
	else npm i; fi
COPY . .
RUN npm run build || true
EXPOSE 3000
CMD ["npm","run","dev"]
