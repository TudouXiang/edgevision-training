import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const apiPort = Number(loadEnv(mode, '.', 'EDGEVISION_DEV_').EDGEVISION_DEV_API_PORT ?? '8000')
  if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
    throw new Error('EDGEVISION_DEV_API_PORT must be a valid TCP port')
  }
  return {
    plugins: [vue()],
    server: {
      fs: { allow: ['..'] },
      proxy: { '/api/v1': `http://127.0.0.1:${apiPort}` },
    },
  }
})
