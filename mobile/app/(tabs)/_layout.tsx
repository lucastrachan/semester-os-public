import { Platform, StyleSheet } from 'react-native'
import { Tabs } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../../src/theme/ThemeProvider'

type Icon = keyof typeof Ionicons.glyphMap
const TABS: { name: string; title: string; icon: Icon; iconOn: Icon }[] = [
  { name: 'today', title: 'Today', icon: 'sunny-outline', iconOn: 'sunny' },
  { name: 'study', title: 'Study', icon: 'school-outline', iconOn: 'school' },
  { name: 'calendar', title: 'Calendar', icon: 'calendar-outline', iconOn: 'calendar' },
  { name: 'books', title: 'Books', icon: 'book-outline', iconOn: 'book' },
  { name: 'settings', title: 'Settings', icon: 'settings-outline', iconOn: 'settings' },
]

export default function TabsLayout() {
  const t = useTheme()
  return (
    <Tabs
      screenOptions={{
        headerShown: false, // each tab owns a native stack with its own header
        tabBarActiveTintColor: t.accentStrong,
        tabBarInactiveTintColor: t.muted,
        tabBarStyle: Platform.select({
          ios: { backgroundColor: t.surface, borderTopColor: t.border, borderTopWidth: StyleSheet.hairlineWidth },
          default: { backgroundColor: t.surface, borderTopWidth: 0, elevation: 8 },
        }),
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        tabBarItemStyle: Platform.OS === 'android' ? { paddingVertical: 4 } : undefined,
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused, color, size }) => (
              <Ionicons name={focused ? tab.iconOn : tab.icon} size={size} color={color} />
            ),
          }}
        />
      ))}
    </Tabs>
  )
}
