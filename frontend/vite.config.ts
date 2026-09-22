import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks: (id: string) => {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('recharts')) return 'charts';
          if (id.includes('@tanstack/react-query') || id.includes('/axios/')) return 'data';
          if (id.includes('react-router-dom') || /\/react(-dom)?\//.test(id)) return 'vendor';
          return undefined;
        },
      },
    },
  },
})
