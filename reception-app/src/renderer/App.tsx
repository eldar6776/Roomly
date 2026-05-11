import React, { useState, useEffect } from 'react';
import LoginPage from './pages/Login';
import ReceptionView from './pages/Reception/ReceptionView';
import ManagerView from './pages/Manager/ManagerView';
import { ToastProvider } from './components/ui/toast';
import { ConfirmDialogProvider } from './components/ui/confirm-dialog';

type UserRole = 'reception' | 'manager' | null;

type PythonStatus = 'checking' | 'ok' | 'missing' | 'pip_error';

function App() {
  const [userRole, setUserRole] = useState<UserRole>(null);
  const [pythonStatus, setPythonStatus] = useState<PythonStatus>('checking');
  const [pythonDetails, setPythonDetails] = useState<string>('');

  useEffect(() => {
    window.electronAPI.python.checkAndInstall().then((result: any) => {
      if (!result.pythonFound) {
        setPythonStatus('missing');
      } else if (!result.pipOk) {
        setPythonStatus('pip_error');
        setPythonDetails(result.pipOutput || '');
      } else {
        setPythonStatus('ok');
      }
    }).catch(() => {
      setPythonStatus('missing');
    });
  }, []);

  const handleLogin = (role: UserRole) => {
    setUserRole(role);
  };

  const handleLogout = () => {
    setUserRole(null);
  };

  return (
    <ToastProvider>
      <ConfirmDialogProvider>
        <div className="h-screen w-screen overflow-hidden bg-background">
      {/* Python status banner */}
      {pythonStatus === 'missing' && (
        <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between bg-red-900 border-b border-red-700 px-4 py-2 text-sm text-white">
          <span>⚠️ Python nije instaliran na ovom računaru. Printer i čitač kartica neće raditi.</span>
          <button
            onClick={() => window.electronAPI.python.openDownload()}
            className="ml-4 rounded bg-white px-3 py-1 text-red-900 font-semibold hover:bg-red-100"
          >
            Preuzmi Python
          </button>
        </div>
      )}
      {pythonStatus === 'pip_error' && (
        <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between bg-yellow-800 border-b border-yellow-600 px-4 py-2 text-sm text-white">
          <span>⚠️ Python pronađen, ali instalacija biblioteka nije uspjela. Printer može imati problema.</span>
          <span className="ml-4 text-yellow-200 text-xs truncate max-w-md" title={pythonDetails}>{pythonDetails.split('\n')[0]}</span>
        </div>
      )}

      {!userRole && <LoginPage onLogin={handleLogin} />}
      {userRole === 'reception' && <ReceptionView onLogout={handleLogout} />}
      {userRole === 'manager' && <ManagerView onLogout={handleLogout} />}
        </div>
      </ConfirmDialogProvider>
    </ToastProvider>
  );
}

export default App;
