import { createHash } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2026-11-06',
  ssr: false,
  spaLoadingTemplate: false,
  features: { inlineStyles: false },
  experimental: { entryImportMap: false },
  devtools: { enabled: false },
  app: {
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      title: '拾存 · Telegram 资源工作台',
      meta: [{ name: 'theme-color', content: '#eef2f6' }],
    },
  },
  css: ['~/assets/main.css'],
  vite: { plugins: [tailwindcss()] },
  nitro: {
    output: { publicDir: fileURLToPath(new URL('../src/telegram_file_downloader/static', import.meta.url)) },
    devProxy: { '/api': { target: 'http://127.0.0.1:18880/api', changeOrigin: false } },
    hooks: {
      async 'prerender:generate'(route, nitro) {
        const html = route.contents
        if (!route.fileName?.endsWith('.html') || !html) return
        const bootstrap = /<script>(window\.__NUXT__=[\s\S]*?)<\/script>/
        const source = bootstrap.exec(html)?.[1]
        if (!source) return
        // Keep Nuxt's executable bootstrap same-origin without relaxing FastAPI's CSP.
        const name = `nuxt-bootstrap-${createHash('sha256').update(source).digest('hex').slice(0, 16)}.js`
        await writeFile(join(nitro.options.output.publicDir, name), source)
        route.contents = html.replace(bootstrap, `<script src="/${name}"></script>`)
      },
    },
  },
})
