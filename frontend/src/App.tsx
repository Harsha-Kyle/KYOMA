import './App.css'
import { useState } from 'react'
import { ThemeProvider } from "@/components/theme-provider"
import Mainpage from './pages/mainpage'
import { Toaster } from "@/components/ui/sonner"
import LoadingScreen from '@/components/loading-screen'
import { SettingsProvider } from '@/context/SettingsContext'

function App() {
  const [isLoaded, setIsLoaded] = useState(false)

  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <SettingsProvider>
        {!isLoaded && <LoadingScreen onLoaded={() => setIsLoaded(true)} />}
        {isLoaded && <Mainpage />}
        <Toaster />
      </SettingsProvider>
    </ThemeProvider>
  )
}

export default App
