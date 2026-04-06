/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        sand: '#f6efe7',
        cream: '#fffaf4',
        ink: '#1f2937',
        coral: '#e97352',
        sage: '#91a08b',
        wheat: '#e5d1b8',
      },
      fontFamily: {
        sans: ['"SUIT Variable"', '"Pretendard Variable"', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 24px 80px rgba(31, 41, 55, 0.12)',
      },
      backgroundImage: {
        grid:
          'linear-gradient(to right, rgba(31, 41, 55, 0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(31, 41, 55, 0.05) 1px, transparent 1px)',
      },
    },
  },
  plugins: [],
};
