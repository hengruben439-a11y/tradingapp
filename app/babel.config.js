module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    [
      'module:react-native-dotenv',
      {
        moduleName: '@env',
        path: '.env',
        blacklist: null,
        whitelist: ['API_BASE_URL'],
        safe: false,
        allowUndefined: true,
      },
    ],
    // react-native-reanimated must be listed last
    'react-native-reanimated/plugin',
  ],
};
