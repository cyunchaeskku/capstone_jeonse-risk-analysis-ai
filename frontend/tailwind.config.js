/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        sand: '#eef4df',
        cream: '#f6fbf2',
        ink: '#124633',
        coral: '#8dc63f',
        sage: '#4f7f5e',
        wheat: '#d9e9bf',
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
