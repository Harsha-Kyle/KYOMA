import './App.css'
import { useState } from 'react'
import { ThemeProvider } from "@/components/theme-provider"
import Mainpage from './pages/mainpage'
import { Toaster } from "@/components/ui/sonner"
import LoadingScreen from '@/components/loading-screen'
import { SettingsProvider } from '@/context/SettingsContext'
import ErrorBoundary from '@/components/error-boundary'

function App() {
  const [isLoaded, setIsLoaded] = useState(false)

  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
        {!isLoaded && <LoadingScreen onLoaded={() => setIsLoaded(true)} />}
        {isLoaded && (
          <SettingsProvider>
            <Mainpage />
            <Toaster />
          </SettingsProvider>
        )}
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App
