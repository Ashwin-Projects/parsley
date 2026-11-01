const paths = {
  leaf: 'M12 20v-9m0 5C3 18 2 7 9 8c0-7 10-7 10 0 7 1 5 10-3 9',
  arrow: 'M5 12h14m-6-6 6 6-6 6', play: 'm8 5 11 7-11 7Z',
  undo: 'M9 5 4 10l5 5M4 10h10a6 6 0 0 1 0 12', reset: 'M20 7v5h-5M19 12a7 7 0 1 0-2 5',
  copy: 'M9 9h11v12H9ZM5 16H3V3h12v2', download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  moon: 'M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z',
  sun: 'M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  help: 'M9 8a3 3 0 1 1 4 3c-1 1-1 2-1 3m0 3h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  code: 'm8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16',
  chat: 'M21 15a3 3 0 0 1-3 3H8l-5 4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3Z', close: 'm6 6 12 12M6 18 18 6',
} as const;
export function Icon({ name, size = 18 }: { name: keyof typeof paths; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
