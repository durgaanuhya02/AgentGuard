# AgentGuard dashboard (Next.js)
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Rewrites to the API are fixed at build time.
ARG AGENTGUARD_API_URL=http://api:8000
ENV AGENTGUARD_API_URL=$AGENTGUARD_API_URL
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3001
CMD ["npm", "start", "--", "-p", "3001"]
