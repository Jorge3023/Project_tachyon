import Sidebar from '../components/Sidebar'

export default function AppLayout({ children }) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      {children}
    </div>
  )
}
