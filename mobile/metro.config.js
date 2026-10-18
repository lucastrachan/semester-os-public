// Lets Metro bundle the plain-TypeScript ../shared folder as the module "shared".
const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

const config = getDefaultConfig(__dirname)
const shared = path.resolve(__dirname, '../shared')
config.watchFolders = [...(config.watchFolders ?? []), shared]
config.resolver.extraNodeModules = { ...(config.resolver.extraNodeModules ?? {}), shared }
module.exports = config
