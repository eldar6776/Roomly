import React, { useState, useEffect } from 'react';
import { Button } from '../../components/ui/button';
import { Label } from '../../components/ui/label';
import { Input } from '../../components/ui/input';
import { DatePicker } from '../../components/ui/date-picker';
import { Room, Log, Guest } from '@shared/types';
import LogsViewer from '../../components/LogsViewer';
import { useToast } from '../../components/ui/toast';
import { useConfirm } from '../../components/ui/confirm-dialog';

interface ManagerViewProps {
  onLogout: () => void;
}

type TabType = 'dashboard' | 'logs' | 'settings';

export default function ManagerView({ onLogout }: ManagerViewProps) {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [rooms, setRooms] = useState<Room[]>([]);
  const [logs, setLogs] = useState<Log[]>([]);
  const [guests, setGuests] = useState<Guest[]>([]);
  const [loading, setLoading] = useState(true);

  // Card reader state
  const [cardReaderAvailable, setCardReaderAvailable] = useState(false);
  const [staffCardDate, setStaffCardDate] = useState('');
  const [maidCardLoading, setMaidCardLoading] = useState(false);
  const [managerCardLoading, setManagerCardLoading] = useState(false);

  // Settings state
  const [receptionPin, setReceptionPin] = useState('');
  const [managerPin, setManagerPin] = useState('');
  const [maidPin, setMaidPin] = useState('');
  const [servicePin, setServicePin] = useState('');
  const [checkoutTime, setCheckoutTime] = useState('12:00');
  const [defaultTempDay, setDefaultTempDay] = useState(22);
  const [defaultTempNight, setDefaultTempNight] = useState(20);
  const [defaultLanguage, setDefaultLanguage] = useState('srb');
  const { toast } = useToast();
  const confirm = useConfirm();

  // Load dashboard data
  useEffect(() => {
    const loadData = async () => {
      try {
        const [roomsData, logsData, guestsData] = await Promise.all([
          window.electronAPI.rooms.getAll(),
          window.electronAPI.database.logs.getAll({}),
          window.electronAPI.database.guests.getActive(),
        ]);

        setRooms(roomsData);
        setLogs(logsData.slice(0, 10)); // Last 10 logs
        setGuests(guestsData);
      } catch (error) {
        console.error('Failed to load data:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // Load settings
  useEffect(() => {
    const loadSettings = async () => {
      try {
        // Dobavi staff PIN-ove od RPI-a (single source of truth)
        const staffPins = await window.electronAPI.settings.getStaffPins();
        
        // Učitaj ostale postavke iz lokalne baze
        const [checkoutTimeSetting, tempDay, tempNight, language] = await Promise.all([
          window.electronAPI.settings.get('checkout_time'),
          window.electronAPI.settings.get('default_temp_day'),
          window.electronAPI.settings.get('default_temp_night'),
          window.electronAPI.settings.get('default_language'),
        ]);

        // Postavi staff PIN-ove iz RPI-a
        setReceptionPin(staffPins.reception);
        setManagerPin(staffPins.manager);
        setMaidPin(staffPins.maid);
        setServicePin(staffPins.service);
        
        // Postavi ostale lokalne postavke
        if (checkoutTimeSetting) setCheckoutTime(checkoutTimeSetting);
        if (tempDay) setDefaultTempDay(Number(tempDay));
        if (tempNight) setDefaultTempNight(Number(tempNight));
        if (language) setDefaultLanguage(language);
      } catch (error) {
        console.error('Failed to load settings:', error);
      }
    };

    if (activeTab === 'settings') {
      loadSettings();
      // Initialise default date for staff cards when entering settings
      if (!staffCardDate) {
        const nextMonth = new Date();
        nextMonth.setMonth(nextMonth.getMonth() + 1);
        setStaffCardDate(nextMonth.toISOString().split('T')[0]);
      }
      // Check card reader availability
      window.electronAPI.cards.checkAvailability()
        .then((res: { available: boolean }) => setCardReaderAvailable(Boolean(res?.available)))
        .catch(() => setCardReaderAvailable(false));
    }
  }, [activeTab]);

  const handleSaveReceptionPin = async () => {
    if (receptionPin.length !== 4) {
      toast.warning('PIN mora biti 4 cifre');
      return;
    }

    try {
      await window.electronAPI.settings.set('reception_pin', receptionPin);
      toast.success('Reception PIN je ažuriran');
    } catch (error) {
      console.error('Failed to update PIN:', error);
      toast.error('Greška pri čuvanju PIN-a');
    }
  };

  const handleSaveManagerPin = async () => {
    if (managerPin.length !== 4) {
      toast.warning('PIN mora biti 4 cifre');
      return;
    }

    const ok = await confirm({
      title: 'Promijeniti Manager PIN?',
      message: 'Ovo će ažurirati Manager PIN na svim online sobama i sačuvati ga lokalno.',
      confirmLabel: 'Potvrdi',
      destructive: true,
    });
    if (!ok) return;

    try {
      // Korak 1: Dobavi trenutni PIN od RPI-a (server je jedini izvor istine)
      const staffPins = await window.electronAPI.settings.getStaffPins();
      const currentPin = staffPins.manager;

      // Korak 2: Pošalji na server (config.json + EEPROM kontroleri)
      const result = await window.electronAPI.settings.changeManagerPin(currentPin, managerPin);

      // Korak 3: Tek nakon server potvrde → upiši u lokalni SQLite (za APP login)
      await window.electronAPI.settings.set('manager_pin', managerPin);

      // Korak 4: Osvježi prikaz iz servera
      const updatedPins = await window.electronAPI.settings.getStaffPins();
      setManagerPin(updatedPins.manager);

      if (result.failed > 0) {
        toast.warning(`Manager PIN promijenjen. Uspješno: ${result.updated}/${result.total} soba. ${result.failed} offline — sync automatski.`);
      } else {
        toast.success(`Manager PIN uspješno promijenjen na svih ${result.updated} soba.`);
      }
    } catch (error) {
      console.error('Failed to update Manager PIN:', error);
      toast.error('Greška pri promjeni Manager PIN-a: ' + (error as Error).message);
    }
  };

  const handleChangeMaidPin = async () => {
    if (maidPin.length !== 4) {
      toast.warning('PIN mora biti 4 cifre');
      return;
    }

    const ok = await confirm({
      title: 'Promijeniti PIN sobarice?',
      message: 'Ovo će ažurirati PIN sobarice na svim online sobama.',
      confirmLabel: 'Potvrdi',
      destructive: true,
    });
    if (!ok) return;

    try {
      // Dobavi trenutni PIN direktno od RPI-a (single source of truth)
      const staffPins = await window.electronAPI.settings.getStaffPins();
      const currentPin = staffPins.maid;
      
      const result = await window.electronAPI.settings.changeMaidPin(currentPin, maidPin);

      // Osvježi prikaz nakon uspješne promjene
      const updatedPins = await window.electronAPI.settings.getStaffPins();
      setMaidPin(updatedPins.maid);

      if (result.failed > 0) {
        toast.warning(`PIN sobarice promijenjen. Uspješno: ${result.updated}/${result.total} soba. ${result.failed} offline — sync automatski.`);
      } else {
        toast.success(`PIN sobarice uspješno promijenjen na svih ${result.updated} soba.`);
      }
    } catch (error) {
      console.error('Failed to update Maid PIN:', error);
      toast.error('Greška pri promjeni PIN-a sobarice: ' + (error as Error).message);
    }
  };

  const handleChangeServicePin = async () => {
    if (servicePin.length !== 5) {
      toast.warning('Service PIN mora biti 5 cifara');
      return;
    }

    const ok = await confirm({
      title: 'Promijeniti Service PIN?',
      message: 'Ovo će ažurirati Service PIN na svim online sobama.',
      confirmLabel: 'Potvrdi',
      destructive: true,
    });
    if (!ok) return;

    try {
      // Dobavi trenutni PIN direktno od RPI-a (single source of truth)
      const staffPins = await window.electronAPI.settings.getStaffPins();
      const currentPin = staffPins.service;
      
      const result = await window.electronAPI.settings.changeServicePin(currentPin, servicePin);

      // Osvježi prikaz nakon uspješne promjene
      const updatedPins = await window.electronAPI.settings.getStaffPins();
      setServicePin(updatedPins.service);

      if (result.failed > 0) {
        toast.warning(`Service PIN promijenjen. Uspješno: ${result.updated}/${result.total} soba. ${result.failed} offline — sync automatski.`);
      } else {
        toast.success(`Service PIN uspješno promijenjen na svih ${result.updated} soba.`);
      }
    } catch (error) {
      console.error('Failed to update Service PIN:', error);
      toast.error('Greška pri promjeni Service PIN-a: ' + (error as Error).message);
    }
  };

  const handleWriteStaffCard = async (cardType: 'H' | 'M') => {
    if (!staffCardDate) {
      toast.warning('Odaberite datum važenja kartice');
      return;
    }

    const cardLabel = cardType === 'H' ? 'sobarice' : 'managera';
    const ok = await confirm({
      title: `Upisati karticu ${cardLabel}?`,
      message: `Kartica će važiti do: ${staffCardDate}`,
      confirmLabel: 'Upiši karticu',
    });
    if (!ok) return;

    if (cardType === 'H') setMaidCardLoading(true);
    else setManagerCardLoading(true);

    try {
      const result = await (window.electronAPI.cards as any).writeStaffCard({
        cardType,
        checkOutDate: staffCardDate,
        checkOutTime: '23:59',
      });

      if (result.ok) {
        toast.success(`Kartica ${cardLabel} uspješno programirana. Važi do: ${staffCardDate}`);
      } else {
        toast.error(`Greška pri upisu kartice: ${result.message}`);
      }
    } catch (error) {
      console.error('Staff card write failed:', error);
      toast.error('Greška: ' + (error as Error).message);
    } finally {
      if (cardType === 'H') setMaidCardLoading(false);
      else setManagerCardLoading(false);
    }
  };

  const handleSaveDefaults = async () => {
    try {
      await Promise.all([
        window.electronAPI.settings.set('checkout_time', checkoutTime),
        window.electronAPI.settings.set('default_temp_day', defaultTempDay.toString()),
        window.electronAPI.settings.set('default_temp_night', defaultTempNight.toString()),
        window.electronAPI.settings.set('default_language', defaultLanguage),
      ]);
      toast.success('Zadane postavke su sačuvane');
    } catch (error) {
      console.error('Failed to save defaults:', error);
      toast.error('Greška pri čuvanju postavki');
    }
  };

  // Stats - koristi istu logiku kao Reception
  const stats = {
    totalRooms: rooms.length,
    available: rooms.filter((r) => r.online && !r.active_pin && !r.card_inserted).length,
    checkedIn: rooms.filter((r) => r.active_pin && !r.card_inserted).length,
    occupied: rooms.filter((r) => r.card_inserted).length,
    offline: rooms.filter((r) => !r.online).length,
  };

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card shadow-lg flex-shrink-0">
        <div className="container mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-3xl font-bold">Manager Dashboard</h1>
            <Button onClick={onLogout} variant="destructive">
              Logout
            </Button>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mt-4">
            <Button
              onClick={() => setActiveTab('dashboard')}
              variant={activeTab === 'dashboard' ? 'default' : 'outline'}
            >
              Dashboard
            </Button>
            <Button
              onClick={() => setActiveTab('logs')}
              variant={activeTab === 'logs' ? 'default' : 'outline'}
            >
              Logs
            </Button>
            <Button
              onClick={() => setActiveTab('settings')}
              variant={activeTab === 'settings' ? 'default' : 'outline'}
            >
              Settings
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="container mx-auto px-4 py-8">
        {loading ? (
          <div className="text-center py-20">
            <div className="text-xl text-muted-foreground">Loading...</div>
          </div>
        ) : (
          <>
            {/* Dashboard Tab */}
            {activeTab === 'dashboard' && (
              <div className="space-y-6">
                {/* Stats Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                  <div className="bg-card p-6 rounded-lg border border-border">
                    <div className="text-sm text-muted-foreground">Total Rooms</div>
                    <div className="text-3xl font-bold mt-2">{stats.totalRooms}</div>
                  </div>
                  <div className="bg-green-500/10 p-6 rounded-lg border border-green-500/30">
                    <div className="text-sm text-green-400">Available</div>
                    <div className="text-3xl font-bold text-green-400 mt-2">{stats.available}</div>
                  </div>
                  <div className="bg-blue-500/10 p-6 rounded-lg border border-blue-500/30">
                    <div className="text-sm text-blue-400">Checked In</div>
                    <div className="text-3xl font-bold text-blue-400 mt-2">{stats.checkedIn}</div>
                  </div>
                  <div className="bg-red-500/10 p-6 rounded-lg border border-red-500/30">
                    <div className="text-sm text-red-400">Occupied</div>
                    <div className="text-3xl font-bold text-red-400 mt-2">{stats.occupied}</div>
                  </div>
                  <div className="bg-yellow-500/10 p-6 rounded-lg border border-yellow-500/30">
                    <div className="text-sm text-yellow-400">Offline</div>
                    <div className="text-3xl font-bold text-yellow-400 mt-2">{stats.offline}</div>
                  </div>
                </div>

                {/* Active Guests */}
                <div className="bg-card p-6 rounded-lg border border-border">
                  <h2 className="text-xl font-semibold mb-4">Active Guests</h2>
                  {guests.length === 0 ? (
                    <p className="text-muted-foreground">No active guests</p>
                  ) : (
                    <div className="space-y-3">
                      {guests.map((guest) => {
                        const room = rooms.find(r => r.room_number === guest.room_number);
                        return (
                          <div key={guest.id} className="flex justify-between items-center p-3 bg-background/50 rounded">
                            <div>
                              <div className="font-semibold">Room {guest.room_number}</div>
                              <div className="text-sm text-muted-foreground">
                                PIN: {room?.active_pin || 'N/A'}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-sm text-muted-foreground">Check-out</div>
                              <div className="text-sm font-semibold">
                                {new Date(guest.check_out_date).toLocaleDateString()}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Recent Logs */}
                <div className="bg-card p-6 rounded-lg border border-border">
                  <h2 className="text-xl font-semibold mb-4">Recent Activity</h2>
                  {logs.length === 0 ? (
                    <p className="text-muted-foreground">No recent activity</p>
                  ) : (
                    <div className="space-y-2">
                      {logs.map((log) => (
                        <div key={log.id} className="flex justify-between items-start p-3 bg-background/50 rounded text-sm">
                          <div className="flex-1">
                            <span className="font-semibold">Room {log.room_number}</span>
                            {' - '}
                            <span className="text-muted-foreground">{log.description}</span>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {new Date(log.timestamp).toLocaleString()}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Logs Tab */}
            {activeTab === 'logs' && (
              <LogsViewer rooms={rooms} />
            )}

            {/* Settings Tab */}
            {activeTab === 'settings' && (
              <div className="space-y-6">
                {/* APP PIN Settings (Stored in SQLite) */}
                <div className="bg-card p-6 rounded-lg border border-primary/50 shadow-lg">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-2 h-8 bg-primary rounded"></div>
                    <div>
                      <h2 className="text-2xl font-semibold">🔐 Application PIN Codes</h2>
                      <p className="text-sm text-muted-foreground">Stored in local SQLite database</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Reception PIN */}
                    <div className="space-y-3 p-4 bg-primary/5 rounded-lg border border-primary/20">
                      <Label className="text-lg font-semibold">Reception PIN</Label>
                      <p className="text-xs text-muted-foreground">For reception staff access to APP</p>
                      <Input
                        type="text"
                        maxLength={4}
                        value={receptionPin}
                        onChange={(e) => setReceptionPin(e.target.value.replace(/\D/g, ''))}
                        placeholder="4-digit PIN"
                        className="text-center text-xl tracking-widest font-mono"
                      />
                      <Button onClick={handleSaveReceptionPin} className="w-full">
                        💾 Save Reception PIN
                      </Button>
                      <div className="text-xs text-muted-foreground bg-background/50 p-2 rounded">
                        ⚠️ Default: 1234 (if not set)
                      </div>
                    </div>

                    {/* Manager PIN */}
                    <div className="space-y-3 p-4 bg-primary/5 rounded-lg border border-primary/20">
                      <Label className="text-lg font-semibold">Manager PIN</Label>
                      <p className="text-xs text-muted-foreground">For manager access to settings</p>
                      <Input
                        type="text"
                        maxLength={4}
                        value={managerPin}
                        onChange={(e) => setManagerPin(e.target.value.replace(/\D/g, ''))}
                        placeholder="4-digit PIN"
                        className="text-center text-xl tracking-widest font-mono"
                      />
                      <Button onClick={handleSaveManagerPin} className="w-full">
                        💾 Save Manager PIN
                      </Button>
                      <div className="text-xs text-muted-foreground bg-background/50 p-2 rounded">
                        ⚠️ Default: 0000 (if not set)
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                    <p className="text-sm text-blue-300">
                      ℹ️ <strong>APP PIN-ovi:</strong> Ovi PIN-ovi kontrolišu pristup aplikaciji i čuvaju se isključivo u lokalnoj SQLite bazi na ovom računaru.
                    </p>
                  </div>
                </div>

                {/* Hardware PIN Settings (Stored in UL Controllers) */}
                <div className="bg-card p-6 rounded-lg border border-border">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-2 h-8 bg-orange-500 rounded"></div>
                    <div>
                      <h2 className="text-2xl font-semibold">🚪 Room Access PIN Codes</h2>
                      <p className="text-sm text-muted-foreground">Stored in UL controllers (EEPROM)</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Maid PIN (Global) */}
                    <div className="space-y-3 p-4 bg-orange-500/5 rounded-lg border border-orange-500/20">
                      <Label className="text-lg font-semibold">Maid PIN</Label>
                      <p className="text-xs text-muted-foreground">For housekeeping room access</p>
                      <Input
                        type="text"
                        maxLength={4}
                        value={maidPin}
                        onChange={(e) => setMaidPin(e.target.value.replace(/\D/g, ''))}
                        placeholder="4-digit PIN"
                        className="text-center text-xl tracking-widest font-mono"
                      />
                      <Button onClick={handleChangeMaidPin} className="w-full" variant="outline">
                        🌐 Update on All Rooms
                      </Button>
                    </div>

                    {/* Service PIN (Global) */}
                    <div className="space-y-3 p-4 bg-orange-500/5 rounded-lg border border-orange-500/20">
                      <Label className="text-lg font-semibold">Service PIN</Label>
                      <p className="text-xs text-muted-foreground">For maintenance room access</p>
                      <Input
                        type="text"
                        maxLength={5}
                        value={servicePin}
                        onChange={(e) => setServicePin(e.target.value.replace(/\D/g, ''))}
                        placeholder="5-digit PIN"
                        className="text-center text-xl tracking-widest font-mono"
                      />
                      <Button onClick={handleChangeServicePin} className="w-full" variant="outline">
                        🌐 Update on All Rooms
                      </Button>
                    </div>
                  </div>

                  <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
                    <p className="text-sm text-orange-300">
                      ⚠️ <strong>Hardware PIN-ovi:</strong> Ovi PIN-ovi se programiraju u UL kontrolere svih soba. Promjena će biti poslata na sve online sobe.
                    </p>
                  </div>
                </div>

                {/* Staff Card Programming – visible only when USB card reader is connected */}
                {cardReaderAvailable && (
                  <div className="bg-card p-6 rounded-lg border border-purple-500/50 shadow-lg">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="w-2 h-8 bg-purple-500 rounded"></div>
                      <div>
                        <h2 className="text-2xl font-semibold">🪪 Programiranje kartica osoblja</h2>
                        <p className="text-sm text-muted-foreground">USB čitač/pisač kartica je priključen</p>
                      </div>
                    </div>

                    {/* Shared date picker */}
                    <div className="mb-6">
                      <Label className="text-base font-semibold">Datum isteka kartice</Label>
                      <div className="mt-2">
                        <DatePicker
                          value={staffCardDate}
                          onChange={setStaffCardDate}
                          min={new Date().toISOString().split('T')[0]}
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Maid card */}
                      <div className="space-y-3 p-4 bg-purple-500/5 rounded-lg border border-purple-500/20">
                        <Label className="text-lg font-semibold">🧹 Kartica sobarice</Label>
                        <p className="text-xs text-muted-foreground">Tip kartice: <code>H</code> – pristup domaćinstvu</p>
                        <Button
                          onClick={() => handleWriteStaffCard('H')}
                          disabled={maidCardLoading || !staffCardDate}
                          className="w-full"
                          variant="outline"
                        >
                          {maidCardLoading ? '⏳ Upisujem...' : '💳 Upiši karticu sobarice'}
                        </Button>
                      </div>

                      {/* Manager card */}
                      <div className="space-y-3 p-4 bg-purple-500/5 rounded-lg border border-purple-500/20">
                        <Label className="text-lg font-semibold">👔 Kartica managera</Label>
                        <p className="text-xs text-muted-foreground">Tip kartice: <code>M</code> – upravljački pristup</p>
                        <Button
                          onClick={() => handleWriteStaffCard('M')}
                          disabled={managerCardLoading || !staffCardDate}
                          className="w-full"
                          variant="outline"
                        >
                          {managerCardLoading ? '⏳ Upisujem...' : '💳 Upiši karticu managera'}
                        </Button>
                      </div>
                    </div>

                    <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
                      <p className="text-sm text-purple-300">
                        ℹ️ <strong>Napomena:</strong> Na kartici se ne upisuje ime ni prezime. SYSID objekta se automatski preuzima iz konfiguracije. Kartica važi do kraja odabranog datuma (23:59).
                      </p>
                    </div>
                  </div>
                )}

                {/* Default Settings */}
                <div className="bg-card p-6 rounded-lg border border-border">
                  <h2 className="text-2xl font-semibold mb-6">Default Settings</h2>
                  
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="checkoutTime">Default Checkout Time</Label>
                      <Input
                        id="checkoutTime"
                        type="time"
                        value={checkoutTime}
                        onChange={(e) => setCheckoutTime(e.target.value)}
                      />
                    </div>

                    <div>
                      <Label htmlFor="tempDay">Default Guest In Temperature: {defaultTempDay}°C</Label>
                      <input
                        id="tempDay"
                        type="range"
                        min="18"
                        max="28"
                        value={defaultTempDay}
                        onChange={(e) => setDefaultTempDay(Number(e.target.value))}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                      />
                    </div>

                    <div>
                      <Label htmlFor="tempNight">Default Guest Out Temperature: {defaultTempNight}°C</Label>
                      <input
                        id="tempNight"
                        type="range"
                        min="18"
                        max="28"
                        value={defaultTempNight}
                        onChange={(e) => setDefaultTempNight(Number(e.target.value))}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                      />
                    </div>

                    <div>
                      <Label htmlFor="language">Default Language</Label>
                      <select
                        id="language"
                        value={defaultLanguage}
                        onChange={(e) => setDefaultLanguage(e.target.value)}
                        className="w-full h-10 rounded-md border border-input bg-background px-3 py-2"
                      >
                        <option value="srb">🇷🇸 Srpski</option>
                        <option value="eng">🇬🇧 English</option>
                        <option value="ger">🇩🇪 Deutsch</option>
                      </select>
                    </div>

                    <Button onClick={handleSaveDefaults} className="w-full" size="lg">
                      Save Default Settings
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
        </div>
      </main>
    </div>
  );
}
