/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: '#ffffff',
                foreground: '#000000',
                primary: {
                    DEFAULT: '#000000',
                    foreground: '#ffffff',
                },
                secondary: {
                    DEFAULT: '#f3f4f6',
                    foreground: '#1f2937',
                },
                accent: {
                    DEFAULT: '#3b82f6',
                    foreground: '#ffffff',
                },
                border: '#e5e7eb',
            },
        },
    },
    plugins: [],
}
