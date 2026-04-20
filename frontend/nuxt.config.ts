// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  
  modules: ['@nuxtjs/tailwindcss'],
  
  tailwindcss: {
    cssPath: '~/assets/css/tailwind.css',
    configPath: 'tailwind.config.js'
  },
  
  nitro: {
    runtimeConfig: {
      dbHost: process.env.DB_HOST || '192.168.100.4',
      dbPort: process.env.DB_PORT || 3306,
      dbUser: process.env.DB_USER || 'root',
      dbPassword: process.env.DB_PASSWORD || 'ulikem00n',
      dbDatabase: process.env.DB_DATABASE || 'xhs_notes'
    }
  },
  
  devServer: {
    port: 5020,
    host: '0.0.0.0'
  }
})