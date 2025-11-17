import { createFileRoute } from '@tanstack/react-router'
import logo from '../logo.jpg'

export const Route = createFileRoute('/')({
  component: App,
})

function App() {
  return (
    <div className="text-center">
      <header className="min-h-screen flex flex-col items-center justify-center text-[calc(10px+2vmin)]">
        <img
          src={logo}
          className="h-[40vmin] pointer-events-none"
          alt="logo"
        />
      </header>
    </div>
  )
}
