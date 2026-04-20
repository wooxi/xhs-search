/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/**/*.vue",
    "./app/**/*.js",
    "./app/**/*.ts",
    "./components/**/*.vue",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.js",
    "./plugins/**/*.ts"
  ],
  theme: {
    extend: {
      colors: {
        'xhs-red': '#fe2c55',
        'xhs-bg': '#f5f5f5'
      }
    }
  },
  plugins: []
}