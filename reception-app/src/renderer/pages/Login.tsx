import React, { useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';

interface LoginPageProps {
  onLogin: (role: 'reception' | 'manager') => void;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handlePinChange = (value: string) => {
    // Only allow digits
    if (/^\d*$/.test(value) && value.length <= 4) {
      setPin(value);
      setError('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (pin.length !== 4) {
      setError('PIN mora imati 4 cifre');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Get PINs from database
      console.log('Fetching PINs from database...');
      const receptionPin = await window.electronAPI.settings.get('reception_pin');
      const managerPin = await window.electronAPI.settings.get('manager_pin');

      console.log('Reception PIN from DB:', receptionPin);
      console.log('Manager PIN from DB:', managerPin);
      console.log('Entered PIN:', pin);

      if (pin === receptionPin) {
        console.log('Match: Reception PIN');
        onLogin('reception');
      } else if (pin === managerPin) {
        console.log('Match: Manager PIN');
        onLogin('manager');
      } else {
        console.log('No match - invalid PIN');
        setError('Netačan PIN');
        setPin('');
      }
    } catch (err) {
      console.error('Login error:', err);
      setError('Greška pri prijavi: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-gradient-to-br from-background to-secondary">
      <div className="w-full max-w-md animate-fade-in">
        <div className="rounded-lg border border-border bg-card p-8 shadow-2xl">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className="mb-4 flex justify-center">
              <div className="rounded-full bg-primary p-4">
                <KeyRound className="h-8 w-8 text-primary-foreground" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-foreground">Toplik Smart Hotel</h1>
            <p className="mt-2 text-muted-foreground">Reception Desktop Application</p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="pin" className="mb-2 block text-sm font-medium text-foreground">
                Unesite PIN
              </label>
              <input
                id="pin"
                type="password"
                inputMode="numeric"
                value={pin}
                onChange={(e) => handlePinChange(e.target.value)}
                placeholder="••••"
                className="w-full rounded-md border border-input bg-background px-4 py-3 text-center text-2xl tracking-widest text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
                maxLength={4}
                autoFocus
                disabled={loading}
              />
              {error && (
                <p className="mt-2 text-sm text-destructive animate-slide-in">{error}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || pin.length !== 4}
              className="w-full rounded-md bg-primary px-4 py-3 font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center justify-center">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Provera...
                </span>
              ) : (
                'Prijavi se'
              )}
            </button>
          </form>

        </div>
      </div>
    </div>
  );
}
