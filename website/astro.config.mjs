// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  site: 'https://lxistired.github.io',
  base: '/popmart',
  build: { format: 'directory' },
  vite: {
    build: { rollupOptions: { external: [] } }
  }
});
