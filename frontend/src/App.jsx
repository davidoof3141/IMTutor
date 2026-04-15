import React from 'react';
import { AppProvider, useAppContext } from './context/AppContext';
import Onboarding from './components/Onboarding';
import Dashboard from './components/Dashboard';

function AppContent() {
  const { isOnboarded } = useAppContext();

  return (
    <>
      {isOnboarded ? <Dashboard /> : <Onboarding />}
    </>
  );
}

function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}

export default App;
