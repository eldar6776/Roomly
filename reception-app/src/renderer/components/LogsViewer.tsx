import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { DatePicker } from './ui/date-picker';

type LogCategory = 'system' | 'access' | 'errors';

interface LogsViewerProps {
  rooms: Array<{ room_number: string }>;
}

export default function LogsViewer({ rooms }: LogsViewerProps) {
  const [activeCategory, setActiveCategory] = useState<LogCategory>('system');
  const [systemLogs, setSystemLogs] = useState<any[]>([]);
  const [accessLogs, setAccessLogs] = useState<any[]>([]);
  const [errorLogs, setErrorLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Filters
  const [roomFilter, setRoomFilter] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('');
  const [accessMethodFilter, setAccessMethodFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [showResolvedErrors, setShowResolvedErrors] = useState(false);

  useEffect(() => {
    loadLogs();
  }, [activeCategory, roomFilter, startDate, endDate, eventTypeFilter, accessMethodFilter, severityFilter, showResolvedErrors]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const filters: any = {
        room_number: roomFilter || undefined,
        start_date: startDate || undefined,
        end_date: endDate ? `${endDate}T23:59:59` : undefined,
        limit: 100,
      };

      if (activeCategory === 'system') {
        if (eventTypeFilter) filters.event_type = eventTypeFilter;
        const logs = await window.electronAPI.database.systemLogs.getAll(filters);
        setSystemLogs(logs);
      } else if (activeCategory === 'access') {
        if (accessMethodFilter) filters.access_method = accessMethodFilter;
        const logs = await window.electronAPI.database.accessLogs.getAll(filters);
        setAccessLogs(logs);
      } else if (activeCategory === 'errors') {
        if (severityFilter) filters.severity = severityFilter;
        if (!showResolvedErrors) filters.resolved = false;
        const logs = await window.electronAPI.database.errorLogs.getAll(filters);
        setErrorLogs(logs);
      }
    } catch (error) {
      console.error('Failed to load logs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleResolveError = async (id: number) => {
    try {
      await window.electronAPI.database.errorLogs.resolve(id);
      loadLogs(); // Reload
    } catch (error) {
      console.error('Failed to resolve error:', error);
    }
  };

  const clearFilters = () => {
    setRoomFilter('');
    setStartDate('');
    setEndDate('');
    setEventTypeFilter('');
    setAccessMethodFilter('');
    setSeverityFilter('');
    setShowResolvedErrors(false);
  };

  const getEventIcon = (eventType: string) => {
    const icons: Record<string, string> = {
      CHECK_IN: '✅',
      CHECK_OUT: '🚪',
      EXTEND_STAY: '⏱️',
      PIN_CHANGE: '🔑',
      SETTING_CHANGE: '⚙️',
    };
    return icons[eventType] || '📝';
  };

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      INFO: 'text-blue-400',
      WARNING: 'text-yellow-400',
      ERROR: 'text-red-400',
      CRITICAL: 'text-red-600',
    };
    return colors[severity] || 'text-gray-400';
  };

  return (
    <div className="space-y-6">
      {/* Category Tabs */}
      <div className="flex gap-2">
        <Button
          onClick={() => setActiveCategory('system')}
          variant={activeCategory === 'system' ? 'default' : 'outline'}
          className="flex-1"
        >
          📋 System Logs
        </Button>
        <Button
          onClick={() => setActiveCategory('access')}
          variant={activeCategory === 'access' ? 'default' : 'outline'}
          className="flex-1"
        >
          🚪 Access Logs
        </Button>
        <Button
          onClick={() => setActiveCategory('errors')}
          variant={activeCategory === 'errors' ? 'default' : 'outline'}
          className="flex-1"
        >
          ⚠️ Errors
        </Button>
      </div>

      {/* Filters */}
      <div className="bg-card p-4 rounded-lg border border-border space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Filters</h3>
          <Button onClick={clearFilters} variant="ghost" size="sm">
            🗑️ Clear
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Room Filter */}
          <div>
            <Label>Room</Label>
            <Select value={roomFilter} onValueChange={setRoomFilter}>
              <SelectTrigger>
                <SelectValue placeholder="All Rooms" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All Rooms</SelectItem>
                {rooms.map((room) => (
                  <SelectItem key={room.room_number} value={room.room_number}>
                    Room {room.room_number}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date Range */}
          <div>
            <DatePicker
              label="Start Date"
              value={startDate}
              onChange={setStartDate}
            />
          </div>

          <div>
            <DatePicker
              label="End Date"
              value={endDate}
              onChange={setEndDate}
            />
          </div>

          {/* Category-specific filters */}
          {activeCategory === 'system' && (
            <div>
              <Label>Event Type</Label>
              <Select value={eventTypeFilter} onValueChange={setEventTypeFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All Events" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All Events</SelectItem>
                  <SelectItem value="CHECK_IN">Check-In</SelectItem>
                  <SelectItem value="CHECK_OUT">Check-Out</SelectItem>
                  <SelectItem value="EXTEND_STAY">Extend Stay</SelectItem>
                  <SelectItem value="PIN_CHANGE">PIN Change</SelectItem>
                  <SelectItem value="SETTING_CHANGE">Setting Change</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {activeCategory === 'access' && (
            <div>
              <Label>Access Method</Label>
              <Select value={accessMethodFilter} onValueChange={setAccessMethodFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All Methods" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All Methods</SelectItem>
                  <SelectItem value="PIN">PIN</SelectItem>
                  <SelectItem value="CARD">Card</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {activeCategory === 'errors' && (
            <>
              <div>
                <Label>Severity</Label>
                <Select value={severityFilter} onValueChange={setSeverityFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Severities" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All Severities</SelectItem>
                    <SelectItem value="INFO">Info</SelectItem>
                    <SelectItem value="WARNING">Warning</SelectItem>
                    <SelectItem value="ERROR">Error</SelectItem>
                    <SelectItem value="CRITICAL">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2 pt-6">
                <input
                  type="checkbox"
                  id="showResolved"
                  checked={showResolvedErrors}
                  onChange={(e) => setShowResolvedErrors(e.target.checked)}
                />
                <Label htmlFor="showResolved" className="cursor-pointer">
                  Show Resolved
                </Label>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Logs Display */}
      <div className="bg-card p-6 rounded-lg border border-border">
        {loading ? (
          <p className="text-center text-muted-foreground py-10">Loading...</p>
        ) : (
          <>
            {/* System Logs */}
            {activeCategory === 'system' && (
              <div className="space-y-2">
                {systemLogs.length === 0 ? (
                  <p className="text-center text-muted-foreground py-10">No system logs found</p>
                ) : (
                  systemLogs.map((log) => (
                    <div key={log.id} className="flex justify-between items-start p-4 bg-background/50 rounded border border-border hover:bg-background transition-colors">
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-3">
                          <span className="text-2xl">{getEventIcon(log.event_type)}</span>
                          {log.room_number && (
                            <span className="font-semibold text-primary">Room {log.room_number}</span>
                          )}
                          <span className="px-2 py-0.5 bg-primary/20 text-primary text-xs rounded">
                            {log.event_type}
                          </span>
                          {log.user_role && (
                            <span className="text-xs text-muted-foreground">by {log.user_role}</span>
                          )}
                        </div>
                        <div className="text-sm">{log.description}</div>
                      </div>
                      <div className="text-sm text-muted-foreground whitespace-nowrap ml-4">
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Access Logs */}
            {activeCategory === 'access' && (
              <div className="space-y-2">
                {accessLogs.length === 0 ? (
                  <p className="text-center text-muted-foreground py-10">No access logs found</p>
                ) : (
                  accessLogs.map((log) => {
                    // Determine icon and description based on PIN type
                    let icon = '💳';
                    let description = log.description || 'Access granted';
                    let badgeColor = 'bg-green-500/20 text-green-400';
                    
                    if (log.access_method === 'PIN') {
                      if (log.pin_type === 'GUEST') {
                        icon = '👤';
                        description = 'Gost ušao PIN-om';
                        badgeColor = 'bg-blue-500/20 text-blue-400';
                      } else if (log.pin_type === 'MAID') {
                        icon = '🧹';
                        description = 'Sobarica ušla u sobu';
                        badgeColor = 'bg-purple-500/20 text-purple-400';
                      } else if (log.pin_type === 'MANAGER') {
                        icon = '👔';
                        description = 'Manager pristupio sobi';
                        badgeColor = 'bg-orange-500/20 text-orange-400';
                      } else {
                        icon = '🔑';
                      }
                    }
                    
                    return (
                      <div key={log.id} className="flex justify-between items-start p-4 bg-background/50 rounded border border-border hover:bg-background transition-colors">
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center gap-3">
                            <span className="text-2xl">{icon}</span>
                            <span className="font-semibold text-primary">Room {log.room_number}</span>
                            <span className={`px-2 py-0.5 ${badgeColor} text-xs rounded`}>
                              {log.pin_type ? `${log.access_method} - ${log.pin_type}` : log.access_method}
                            </span>
                          </div>
                          <div className="text-sm">{description}</div>
                          {log.card_id && (
                            <div className="text-xs text-muted-foreground">Card ID: {log.card_id}</div>
                          )}
                        </div>
                        <div className="text-sm text-muted-foreground whitespace-nowrap ml-4">
                          {new Date(log.timestamp).toLocaleString()}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* Error Logs */}
            {activeCategory === 'errors' && (
              <div className="space-y-2">
                {errorLogs.length === 0 ? (
                  <p className="text-center text-muted-foreground py-10">No errors found 🎉</p>
                ) : (
                  errorLogs.map((log) => (
                    <div key={log.id} className={`flex justify-between items-start p-4 bg-background/50 rounded border ${log.resolved ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'} hover:bg-background transition-colors`}>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-3">
                          <span className={`font-semibold ${getSeverityColor(log.severity)}`}>
                            {log.severity}
                          </span>
                          {log.room_number && (
                            <span className="font-semibold text-primary">Room {log.room_number}</span>
                          )}
                          <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded">
                            {log.error_type}
                          </span>
                          {log.resolved && (
                            <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded">
                              ✓ Resolved
                            </span>
                          )}
                        </div>
                        <div className="text-sm font-semibold">{log.message}</div>
                        {log.details && (
                          <div className="text-xs text-muted-foreground bg-background/50 p-2 rounded mt-1">
                            {log.details}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2 ml-4">
                        <div className="text-sm text-muted-foreground whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleString()}
                        </div>
                        {!log.resolved && (
                          <Button
                            onClick={() => handleResolveError(log.id)}
                            variant="outline"
                            size="sm"
                            className="text-xs"
                          >
                            ✓ Mark Resolved
                          </Button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
