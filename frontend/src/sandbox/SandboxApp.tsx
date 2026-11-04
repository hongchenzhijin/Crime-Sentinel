import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { sandboxApi, sandboxJoin } from '../lib/api'
import type { SbGroup, SbPost, SbReport, SbThread, SbUser } from '../lib/types'
import { useAsync } from '../lib/useAsync'

// A simulated social network so the Sentinel agent can be demonstrated end to end.
// Everything shown here is fictional. The layout mirrors a familiar social app so the demo reads naturally.

const BLUE = '#0866ff'
const FONT = '"Segoe UI Historic", "Segoe UI", Helvetica, Arial, sans-serif'
type Route = { page: 'home' } | { page: 'groups' } | { page: 'group'; id: string } | { page: 'messages' } | { page: 'integrity' }

const parseRoute = (): Route => {
  const parts = window.location.hash.replace(/^#fb\/?/, '').split('?')[0].split('/')
  if (parts[0] === 'group' && parts[1]) return { page: 'group', id: parts[1] }
  if (parts[0] === 'groups') return { page: 'groups' }
  if (parts[0] === 'messages') return { page: 'messages' }
  if (parts[0] === 'integrity') return { page: 'integrity' }
  return { page: 'home' }
}
const go = (path: string) => (window.location.hash = `fb${path}`)

const VIEWERS = [
  { id: 'u_persona', label: 'Alex Tan', sub: 'Sentinel research persona' },
  { id: 'u_viewer', label: 'Public visitor', sub: 'Ordinary user (you)' },
  { id: 'u_integrity', label: 'Meta Integrity reviewer', sub: 'Trust & safety staff' },
]

function useTick(ms: number) {
  const [t, setT] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setT((x) => x + 1), ms)
    return () => clearInterval(id)
  }, [ms])
  return t
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

const compact = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(/\.0$/, '')}M` : n >= 1e4 ? `${(n / 1e3).toFixed(1).replace(/\.0$/, '')}K` : n.toLocaleString())

export function Avatar({ user, size = 40, online }: { user: SbUser; size?: number; online?: boolean }) {
  const initials = user.name.replace(/[^\p{L}\p{N} ]/gu, '').split(/[ ._]/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-hidden>
      <div className="flex h-full w-full items-center justify-center rounded-full font-semibold text-white"
        style={{ background: `linear-gradient(145deg, ${user.avatar_color}, ${user.avatar_color}cc)`, fontSize: size * 0.38 }}>
        {initials || '?'}
      </div>
      {online && <span className="absolute right-0 bottom-0 rounded-full border-2 border-white bg-[#31a24c]" style={{ width: size * 0.3, height: size * 0.3 }} />}
    </div>
  )
}

// ---------- icons (simple inline SVG so nothing depends on an icon font) ----------
type IconProps = { className?: string; style?: CSSProperties }
const svg = (d: ReactNode, vb = '0 0 24 24') => ({ className = 'h-5 w-5', style }: IconProps) => (
  <svg viewBox={vb} fill="currentColor" className={className} style={style} aria-hidden>{d}</svg>
)
const I = {
  home: svg(<path d="M9.5 21v-6.5h5V21h4.8a.7.7 0 0 0 .7-.7V10.6a1 1 0 0 0-.36-.77l-7.3-6.1a1.4 1.4 0 0 0-1.8 0l-7.3 6.1a1 1 0 0 0-.36.77v9.7c0 .39.31.7.7.7z" />),
  groups: svg(<path d="M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm-6.5 1.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zm13 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM12 12.5c-3.3 0-6 2-6 4.5v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2c0-2.5-2.7-4.5-6-4.5zm-7.2 1.2C2.6 14 1 15.4 1 17v1.5a1 1 0 0 0 1 1h2.5V17c0-1.3.1-2.3.3-3.3zm14.4 0c.2 1 .3 2 .3 3.3v2.5H22a1 1 0 0 0 1-1V17c0-1.6-1.6-3-3.8-3.3z" />),
  messenger: svg(<path d="M12 2C6.36 2 2 6.13 2 11.7c0 2.91 1.19 5.44 3.14 7.17.16.14.26.35.27.57l.05 1.78a.8.8 0 0 0 1.13.71l1.98-.87a.8.8 0 0 1 .54-.04c.91.25 1.87.38 2.89.38 5.64 0 10-4.13 10-9.7S17.64 2 12 2zm6 7.46-2.94 4.66a1.5 1.5 0 0 1-2.17.4l-2.34-1.75a.6.6 0 0 0-.72 0l-3.16 2.4c-.42.32-.97-.18-.69-.63l2.94-4.66a1.5 1.5 0 0 1 2.17-.4l2.34 1.75a.6.6 0 0 0 .72 0l3.16-2.4c.42-.32.97.18.69.63z" />),
  bell: svg(<path d="M3 9.5a9 9 0 0 1 18 0v2.9c0 .6.2 1.2.6 1.7l.9 1.2c.9 1.2.05 2.9-1.45 2.9H2.95c-1.5 0-2.35-1.7-1.45-2.9l.9-1.2c.4-.5.6-1.1.6-1.7zM8.5 20h7a3.5 3.5 0 0 1-7 0z" />),
  menu: svg(<path d="M5 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM5 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM5 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />),
  search: svg(<path d="M10 2.5a7.5 7.5 0 0 1 5.96 12.05l5.25 5.24a1 1 0 0 1-1.42 1.42l-5.24-5.25A7.5 7.5 0 1 1 10 2.5zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z" />),
  shield: svg(<path d="M12 1.5 3.5 4.8v6.1c0 5.2 3.6 10 8.5 11.6 4.9-1.6 8.5-6.4 8.5-11.6V4.8zm-1.2 14.8-3.6-3.6 1.4-1.4 2.2 2.2 5-5 1.4 1.4z" />),
  globe: svg(<path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm4.9 6.3h-2.1a10.5 10.5 0 0 0-.9-4 5.6 5.6 0 0 1 3 4zM8 2.5c.6.8 1.3 2.5 1.4 4.8H6.6C6.7 5 7.4 3.3 8 2.5zM6.1 3.3a10.5 10.5 0 0 0-.9 4H3.1a5.6 5.6 0 0 1 3-4zM3.1 8.7h2.1c.1 1.5.4 2.9.9 4a5.6 5.6 0 0 1-3-4zM8 13.5c-.6-.8-1.3-2.5-1.4-4.8h2.8c-.1 2.3-.8 4-1.4 4.8zm1.9-.8c.5-1.1.8-2.5.9-4h2.1a5.6 5.6 0 0 1-3 4z" />, '0 0 16 16'),
  lock: svg(<path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H4a1.5 1.5 0 0 0-1.5 1.5v6A1.5 1.5 0 0 0 4 15h8a1.5 1.5 0 0 0 1.5-1.5v-6A1.5 1.5 0 0 0 12 6h-.5V4.5A3.5 3.5 0 0 0 8 1zm2 5H6V4.5a2 2 0 1 1 4 0z" />, '0 0 16 16'),
  eyeOff: svg(<path d="M1.6 2.6 2.7 1.5l11.8 11.8-1.1 1.1-2.2-2.2A7.6 7.6 0 0 1 8 13c-3.5 0-6.2-2.4-7.4-5 .5-1.2 1.4-2.4 2.6-3.3zM8 3c3.5 0 6.2 2.4 7.4 5a8.6 8.6 0 0 1-1.9 2.6L5.4 3.4C6.2 3.1 7.1 3 8 3z" />, '0 0 16 16'),
  dots: svg(<path d="M6 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm8 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm6 2a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" />),
  close: svg(<path d="M18.7 5.3a1 1 0 0 0-1.4 0L12 10.6 6.7 5.3a1 1 0 0 0-1.4 1.4l5.3 5.3-5.3 5.3a1 1 0 1 0 1.4 1.4l5.3-5.3 5.3 5.3a1 1 0 0 0 1.4-1.4L13.4 12l5.3-5.3a1 1 0 0 0 0-1.4z" />),
  like: svg(<path d="M7 21H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3zm2-11.5 3.6-6.3A1.6 1.6 0 0 1 15.5 4l-.8 5H19a2 2 0 0 1 2 2.3l-1.2 7.6A2.5 2.5 0 0 1 17.3 21H9z" fillRule="evenodd" />),
  comment: svg(<path d="M12 3C6.5 3 2 6.8 2 11.5c0 2.4 1.2 4.6 3.1 6.1L4.5 21l3.7-1.9c1.2.4 2.5.6 3.8.6 5.5 0 10-3.8 10-8.5S17.5 3 12 3zm0 15c-1.2 0-2.3-.2-3.4-.6l-.4-.1-1.6.8.3-1.5-.4-.3C4.9 15 4 13.3 4 11.5 4 7.9 7.6 5 12 5s8 2.9 8 6.5-3.6 6.5-8 6.5z" />),
  share: svg(<path d="M13 4.5V8C6.5 8.5 3 13 3 19.5c2.2-3.3 5.3-4.8 10-5V18l8-6.75z" />),
  photo: svg(<path d="M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm3.5 4a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM5 17.5h14l-4.5-6-3.5 4.5-2.5-3z" />),
  smile: svg(<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM8.5 8a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm7 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM12 18a5.5 5.5 0 0 1-5-3.2h10A5.5 5.5 0 0 1 12 18z" />),
  video: svg(<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h8A2.5 2.5 0 0 1 16 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 3 17.5zm14.5 3 3.4-2.3a.7.7 0 0 1 1.1.6v8.4a.7.7 0 0 1-1.1.6l-3.4-2.3z" />),
  pin: svg(<path d="M14.3 2.3a1 1 0 0 1 1.4 0l6 6a1 1 0 0 1-.3 1.6l-3.2 1.4-2.6 4.4.6 3.3a1 1 0 0 1-1.7.9l-3.7-3.7-5.1 5.1-1.4-1.4 5.1-5.1-3.7-3.7a1 1 0 0 1 .9-1.7l3.3.6 4.4-2.6 1.4-3.2z" />),
  chevron: svg(<path d="M5.3 8.3a1 1 0 0 1 1.4 0L12 13.6l5.3-5.3a1 1 0 1 1 1.4 1.4l-6 6a1 1 0 0 1-1.4 0l-6-6a1 1 0 0 1 0-1.4z" />),
  plus: svg(<path d="M11 4a1 1 0 1 1 2 0v7h7a1 1 0 1 1 0 2h-7v7a1 1 0 1 1-2 0v-7H4a1 1 0 1 1 0-2h7z" />),
  check: svg(<path d="M9.5 16.2 4.8 11.5l-1.4 1.4 6.1 6.1L21 7.5l-1.4-1.4z" />),
  send: svg(<path d="M3.4 20.6 22 12 3.4 3.4l.1 6.7 12.4 1.9-12.4 1.9z" />),
  info: svg(<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2zm0-8h-2V7h2z" />),
  phone: svg(<path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z" />),
  saved: svg(<path d="M6 2h12a1 1 0 0 1 1 1v18.2a.6.6 0 0 1-1 .5l-6-4.5-6 4.5a.6.6 0 0 1-1-.5V3a1 1 0 0 1 1-1z" />),
}

const PrivacyIcon = ({ p, className = 'h-3 w-3' }: { p: SbGroup['privacy']; className?: string }) =>
  p === 'public' ? <I.globe className={className} /> : p === 'private' ? <I.lock className={className} /> : <I.eyeOff className={className} />
const privacyLabel = (p: SbGroup['privacy']) => (p === 'public' ? 'Public group' : p === 'private' ? 'Private group' : 'Secret group')

const Card = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`rounded-lg bg-white shadow-[0_1px_2px_rgba(0,0,0,0.2)] ${className}`}>{children}</div>
)

const GrayBtn = ({ children, onClick, className = '' }: { children: ReactNode; onClick?: () => void; className?: string }) => (
  <button onClick={onClick} className={`flex items-center justify-center gap-1.5 rounded-md bg-[#e4e6eb] px-3 text-[15px] font-semibold hover:bg-[#d8dadf] ${className}`} style={{ height: 36 }}>
    {children}
  </button>
)
const BlueBtn = ({ children, onClick, className = '' }: { children: ReactNode; onClick?: () => void; className?: string }) => (
  <button onClick={onClick} className={`flex items-center justify-center gap-1.5 rounded-md px-3 text-[15px] font-semibold text-white hover:brightness-95 ${className}`} style={{ height: 36, background: BLUE }}>
    {children}
  </button>
)

const GroupThumb = ({ group, size = 36, rounded = 'rounded-lg' }: { group: SbGroup; size?: number; rounded?: string }) => (
  <div className={`shrink-0 ${rounded}`} style={{ width: size, height: size, background: `linear-gradient(135deg, ${group.cover_color}, ${group.cover_color}88 60%, #00000055)` }} />
)

// ---------- shell ----------
export function SandboxApp() {
  const [route, setRoute] = useState<Route>(parseRoute)
  const [viewer, setViewer] = useState(() => new URLSearchParams(window.location.hash.split('?')[1]).get('viewer')
    ?? localStorage.getItem('sb.viewer') ?? 'u_persona')
  const tick = useTick(2500)
  const embed = window.location.hash.includes('embed=1')

  useEffect(() => {
    const on = () => setRoute(parseRoute())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  useEffect(() => {
    localStorage.setItem('sb.viewer', viewer)
  }, [viewer])

  const groups = useAsync(() => sandboxApi.groups(viewer), [viewer, tick])
  const users = useAsync(() => sandboxApi.users(), [])
  const me = users.data?.find((u) => u.id === viewer)
  const others = (users.data ?? []).filter((u) => u.id !== viewer && !u.is_persona)

  return (
    <div className={`${route.page === 'messages' ? 'flex h-screen flex-col' : 'min-h-screen'} bg-[#f0f2f5] text-[#080809]`} style={{ fontFamily: FONT }}>
      <TopBar route={route} viewer={viewer} setViewer={setViewer} me={me} embed={embed} />

      {viewer === 'u_persona' && (
        <div className="flex items-center justify-center gap-2 border-b border-[#c9dcf7] bg-[#ebf3ff] px-4 py-1.5 text-center text-xs text-[#0a3a8a]">
          <I.shield className="h-3.5 w-3.5 shrink-0" />
          <span>Viewing as <strong>Alex Tan</strong>, a governed Crime Sentinel research persona registered with Meta Integrity. It cannot post; every message passes the Safety Governor and a human.</span>
        </div>
      )}

      {route.page === 'messages' ? (
        <Messenger viewer={viewer} tick={tick} />
      ) : route.page === 'group' ? (
        <GroupPage id={route.id} viewer={viewer} tick={tick} groups={groups.data ?? []} />
      ) : (
        <div className="flex justify-between">
          <LeftNav me={me} viewer={viewer} groups={groups.data ?? []} route={route} />
          <main className="min-w-0 flex-1 px-2 py-4 sm:px-4">
            <div className="mx-auto max-w-[680px]">
              {route.page === 'home' && <Home groups={groups.data ?? []} viewer={viewer} me={me} tick={tick} />}
              {route.page === 'groups' && <GroupsDiscover groups={groups.data ?? []} />}
              {route.page === 'integrity' && <Integrity tick={tick} />}
            </div>
          </main>
          <RightRail contacts={others} groups={groups.data ?? []} />
        </div>
      )}
    </div>
  )
}

function TopBar({ route, viewer, setViewer, me, embed }: { route: Route; viewer: string; setViewer: (v: string) => void; me?: SbUser; embed: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const on = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', on)
    return () => document.removeEventListener('mousedown', on)
  }, [])

  const tabs: [string, (p: IconProps) => ReactNode, string, boolean][] = [
    ['', I.home, 'Home', route.page === 'home'],
    ['/groups', I.groups, 'Groups', route.page === 'groups' || route.page === 'group'],
    ...(viewer === 'u_integrity' ? [['/integrity', I.shield, 'Integrity', route.page === 'integrity'] as [string, (p: IconProps) => ReactNode, string, boolean]] : []),
  ]
  const circle = 'flex h-10 w-10 items-center justify-center rounded-full bg-[#e4e6eb] text-[#080809] hover:bg-[#d8dadf]'

  return (
    <header className="sticky top-0 z-30 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.1)]">
      <div className="bg-[#fff4ce] px-4 py-0.5 text-center text-[11px] text-[#6b5400]">
        Sandbox: simulated social network for the Crime Sentinel demo. All people, groups and posts are fictional.
        {!embed && <a href="#mission" className="ml-2 font-semibold underline">Open Mission Control</a>}
      </div>
      <div className="relative flex h-14 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <button onClick={() => go('')} aria-label="Home" className="flex h-10 w-10 items-center justify-center rounded-full text-[26px] leading-none font-bold text-white" style={{ background: BLUE }}>
            <span className="-mb-1">s</span>
          </button>
          <div className="hidden h-10 w-60 items-center gap-2 rounded-full bg-[#f0f2f5] px-3 text-[15px] text-[#65686c] xl:flex">
            <I.search className="h-4 w-4" /> Search Sandbox
          </div>
          <div className={`${circle} xl:hidden`}><I.search className="h-5 w-5 text-[#65686c]" /></div>
        </div>

        <nav className="absolute left-1/2 hidden h-full -translate-x-1/2 md:flex">
          {tabs.map(([path, Icon, label, active]) => (
            <button key={label} onClick={() => go(path)} title={label}
              className="group relative flex h-full w-[110px] items-center justify-center lg:w-[128px]">
              <span className={`flex h-12 w-full items-center justify-center rounded-lg ${active ? '' : 'group-hover:bg-[#f0f2f5]'}`}>
                <Icon className="h-7 w-7" style={{ color: active ? BLUE : '#65686c' }} />
              </span>
              {active && <span className="absolute right-0 bottom-0 left-0 h-[3px] rounded-t" style={{ background: BLUE }} />}
            </button>
          ))}
        </nav>

        <div ref={ref} className="relative flex items-center gap-2">
          <div className={`${circle} hidden sm:flex`}><I.menu className="h-5 w-5" /></div>
          <button onClick={() => go('/messages')} title="Messenger" className={circle} style={route.page === 'messages' ? { background: '#dfe9f9', color: BLUE } : undefined}>
            <I.messenger className="h-5 w-5" />
          </button>
          <div className={`${circle} relative`}>
            <I.bell className="h-5 w-5" />
            {viewer === 'u_integrity' && <span className="absolute -top-1 -right-1 flex h-[19px] min-w-[19px] items-center justify-center rounded-full bg-[#e41e3f] px-1 text-[12px] font-semibold text-white">!</span>}
          </div>
          <button onClick={() => setOpen(!open)} className="relative rounded-full" aria-label="Switch viewer">
            {me ? <Avatar user={me} size={40} /> : <div className="h-10 w-10 rounded-full bg-[#e4e6eb]" />}
            <span className="absolute -right-0.5 -bottom-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-[#e4e6eb]">
              <I.chevron className="h-2.5 w-2.5" />
            </span>
          </button>
          {open && (
            <div className="absolute top-12 right-0 w-[340px] rounded-lg bg-white p-2 shadow-[0_12px_28px_rgba(0,0,0,0.2),0_2px_4px_rgba(0,0,0,0.1)]">
              <div className="px-2 pt-1 pb-2 text-[13px] font-semibold text-[#65686c]">Switch demo viewer</div>
              {VIEWERS.map((v) => (
                <button key={v.id} onClick={() => { setViewer(v.id); setOpen(false) }}
                  className={`flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-[#f2f2f2] ${v.id === viewer ? 'bg-[#f2f2f2]' : ''}`}>
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#e4e6eb]">
                    {v.id === 'u_integrity' ? <I.shield className="h-5 w-5" /> : v.id === 'u_persona' ? <I.saved className="h-4 w-4" /> : <I.groups className="h-5 w-5" />}
                  </div>
                  <span className="flex-1">
                    <span className="block text-[15px] font-semibold">{v.label}</span>
                    <span className="block text-[13px] text-[#65686c]">{v.sub}</span>
                  </span>
                  {v.id === viewer && <I.check className="h-5 w-5" style={{ color: BLUE }} />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

function NavRow({ icon, label, sub, onClick, active }: { icon: ReactNode; label: string; sub?: string; onClick?: () => void; active?: boolean }) {
  return (
    <button onClick={onClick} className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-[#e4e6eb] ${active ? 'bg-[#e4e6eb]' : ''}`}>
      {icon}
      <span className="min-w-0">
        <span className="block truncate text-[15px] font-medium">{label}</span>
        {sub && <span className="block truncate text-[12px] text-[#65686c]">{sub}</span>}
      </span>
    </button>
  )
}

const RoundIcon = ({ children, bg = BLUE }: { children: ReactNode; bg?: string }) => (
  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white" style={{ background: bg }}>{children}</div>
)

function LeftNav({ me, viewer, groups, route }: { me?: SbUser; viewer: string; groups: SbGroup[]; route: Route }) {
  const joined = groups.filter((g) => g.viewer_is_member)
  return (
    <aside className="sticky top-[78px] hidden h-[calc(100vh-78px)] w-[300px] shrink-0 overflow-y-auto px-2 py-4 lg:block xl:w-[340px]">
      {me && <NavRow onClick={() => go('')} icon={<Avatar user={me} size={36} />} label={me.name} />}
      <NavRow onClick={() => go('/groups')} active={route.page === 'groups'} icon={<RoundIcon><I.groups className="h-5 w-5" /></RoundIcon>} label="Groups" />
      <NavRow onClick={() => go('/messages')} icon={<RoundIcon bg="linear-gradient(45deg,#0866ff,#a033ff,#ff5c87)"><I.messenger className="h-5 w-5" /></RoundIcon>} label="Messenger" />
      <NavRow icon={<RoundIcon bg="#a033ff"><I.saved className="h-4 w-4" /></RoundIcon>} label="Saved" />
      {viewer === 'u_integrity' && (
        <NavRow onClick={() => go('/integrity')} active={route.page === 'integrity'} icon={<RoundIcon bg="#1b7a3d"><I.shield className="h-5 w-5" /></RoundIcon>} label="Integrity inbox" />
      )}
      <div className="mx-2 my-2 border-t border-[#ced0d4]" />
      <div className="px-2 pt-1 pb-1 text-[17px] font-semibold text-[#65686c]">Your shortcuts</div>
      {(joined.length ? joined : groups).map((g) => (
        <NavRow key={g.id} onClick={() => go(`/group/${g.id}`)} icon={<GroupThumb group={g} />} label={g.name} />
      ))}
    </aside>
  )
}

function RightRail({ contacts, groups }: { contacts: SbUser[]; groups: SbGroup[] }) {
  const suggested = groups.filter((g) => !g.viewer_is_member && g.privacy !== 'secret').slice(0, 2)
  return (
    <aside className="sticky top-[78px] hidden h-[calc(100vh-78px)] w-[300px] shrink-0 overflow-y-auto px-2 py-4 xl:block xl:w-[340px]">
      {suggested.length > 0 && (
        <>
          <div className="px-2 pb-2 text-[17px] font-semibold text-[#65686c]">Suggested groups</div>
          {suggested.map((g) => (
            <button key={g.id} onClick={() => go(`/group/${g.id}`)} className="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-[#e4e6eb]">
              <GroupThumb group={g} size={56} />
              <span className="min-w-0">
                <span className="block truncate text-[15px] font-semibold">{g.name}</span>
                <span className="block text-[13px] text-[#65686c]">{compact(g.member_count)} members</span>
              </span>
            </button>
          ))}
          <div className="mx-2 my-2 border-t border-[#ced0d4]" />
        </>
      )}
      <div className="flex items-center justify-between px-2 pb-1">
        <span className="text-[17px] font-semibold text-[#65686c]">Contacts</span>
        <span className="flex gap-1 text-[#65686c]"><I.search className="h-4 w-4" /><I.dots className="h-4 w-4" /></span>
      </div>
      {contacts.slice(0, 14).map((u, i) => (
        <button key={u.id} onClick={() => go('/messages')} className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-[#e4e6eb]">
          <Avatar user={u} size={36} online={i % 3 !== 2} />
          <span className="truncate text-[15px] font-medium">{u.name}</span>
        </button>
      ))}
    </aside>
  )
}

// ---------- pages ----------
function Composer({ me, viewer, placeholder }: { me?: SbUser; viewer: string; placeholder?: string }) {
  const locked = viewer === 'u_persona'
  return (
    <Card className="px-4 pt-3 pb-2">
      <div className="flex items-center gap-2">
        {me && <Avatar user={me} size={40} />}
        <div className="flex h-10 flex-1 items-center rounded-full bg-[#f0f2f5] px-3 text-[17px] text-[#65686c]" title={locked ? 'Sentinel personas cannot post' : undefined}>
          {locked ? 'Posting is disabled for research personas' : placeholder ?? `What's on your mind, ${me?.name.split(' ')[0] ?? 'friend'}?`}
        </div>
      </div>
      <div className="mt-3 flex border-t border-[#ced0d4] pt-2">
        {[[I.video, 'Live video', '#f02849'], [I.photo, 'Photo/video', '#45bd62'], [I.smile, 'Feeling/activity', '#f7b928']].map(([Icon, label, color]) => {
          const Ic = Icon as (p: IconProps) => ReactNode
          return (
            <div key={label as string} className="flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-[15px] font-semibold text-[#65686c] hover:bg-[#f0f2f5]">
              <Ic className="h-6 w-6" style={{ color: color as string }} /><span className="hidden sm:inline">{label as string}</span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function Home({ groups, viewer, me, tick }: { groups: SbGroup[]; viewer: string; me?: SbUser; tick: number }) {
  const readable = groups.filter((g) => g.can_read_feed)
  return (
    <div className="mx-auto max-w-[590px] space-y-4">
      <Composer me={me} viewer={viewer} />
      {readable.length === 0 && <Card className="p-6 text-center text-[15px] text-[#65686c]">Join groups to see posts in your feed.</Card>}
      {readable.slice(0, 4).map((g) => <GroupFeed key={g.id} group={g} viewer={viewer} tick={tick} limit={2} showGroup me={me} />)}
    </div>
  )
}

function GroupsDiscover({ groups }: { groups: SbGroup[] }) {
  return (
    <Card className="p-4">
      <h2 className="text-xl font-bold">Your groups</h2>
      <p className="text-[15px] text-[#65686c]">Groups you're in and groups you might like.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {groups.map((g) => (
          <div key={g.id} className="overflow-hidden rounded-lg border border-[#dadde1]">
            <button onClick={() => go(`/group/${g.id}`)} className="block h-28 w-full" style={{ background: `linear-gradient(135deg, ${g.cover_color}, ${g.cover_color}99 55%, #000000aa)` }} aria-label={g.name} />
            <div className="p-3">
              <button onClick={() => go(`/group/${g.id}`)} className="block truncate text-[17px] font-semibold hover:underline">{g.name}</button>
              <div className="mt-0.5 flex items-center gap-1 text-[13px] text-[#65686c]"><PrivacyIcon p={g.privacy} /> {privacyLabel(g.privacy)} · {compact(g.member_count)} members</div>
              {g.viewer_is_member
                ? <GrayBtn onClick={() => go(`/group/${g.id}`)} className="mt-3 w-full">View group</GrayBtn>
                : <button onClick={() => go(`/group/${g.id}`)} className="mt-3 h-9 w-full rounded-md bg-[#ebf5ff] text-[15px] font-semibold" style={{ color: BLUE }}>Join group</button>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function GroupPage({ id, viewer, tick, groups }: { id: string; viewer: string; tick: number; groups: SbGroup[] }) {
  const g = useAsync(() => sandboxApi.group(id, viewer), [id, viewer, tick])
  const users = useAsync(() => sandboxApi.users(), [])
  const [joining, setJoining] = useState(false)
  if (g.error) {
    return (
      <div className="mx-auto max-w-[500px] px-4 py-20 text-center">
        <div className="text-[20px] font-bold">This content isn't available right now</div>
        <p className="mt-2 text-[15px] text-[#65686c]">When this happens, it's usually because the owner only shared it with a small group of people, changed who can see it or it's been deleted.</p>
        <BlueBtn onClick={() => go('')} className="mx-auto mt-5 px-10">Go to Feed</BlueBtn>
      </div>
    )
  }
  if (!g.data) return <div className="p-10 text-center text-[#65686c]">Loading…</div>
  const group = g.data
  const me = users.data?.find((u) => u.id === viewer)
  const members = (users.data ?? []).filter((u) => !u.is_persona).slice(0, 8)

  const action = group.viewer_is_member ? (
    <GrayBtn><I.groups className="h-4 w-4" /> Joined <I.chevron className="h-3 w-3" /></GrayBtn>
  ) : group.viewer_request_status === 'pending' ? (
    <GrayBtn>Cancel request</GrayBtn>
  ) : viewer === 'u_persona' ? (
    <GrayBtn className="cursor-default text-[13px] text-[#65686c]"><I.shield className="h-4 w-4" /> Joins via Mission Control</GrayBtn>
  ) : (
    <BlueBtn onClick={() => setJoining(true)}><I.groups className="h-4 w-4" /> Join group</BlueBtn>
  )

  return (
    <div>
      <div className="bg-white shadow-[0_1px_2px_rgba(0,0,0,0.1)]">
        <div className="mx-auto max-w-[1250px]">
          <div className="relative h-[180px] overflow-hidden rounded-b-lg sm:h-[300px] lg:h-[350px]"
            style={{ background: `radial-gradient(circle at 25% 30%, ${group.cover_color}ee, transparent 60%), radial-gradient(circle at 80% 70%, ${group.cover_color}aa, transparent 55%), linear-gradient(160deg, ${group.cover_color}, #101418)` }}>
            <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_60%,rgba(0,0,0,0.35))]" />
          </div>
          <div className="px-4 lg:px-8">
            <div className="flex flex-wrap items-end justify-between gap-3 pt-4 pb-3">
              <div className="min-w-0">
                <h1 className="text-[26px] leading-tight font-bold sm:text-[32px]">{group.name}</h1>
                <div className="mt-1 flex items-center gap-1 text-[15px] text-[#65686c]">
                  <PrivacyIcon p={group.privacy} className="h-3.5 w-3.5" /> {privacyLabel(group.privacy)} · <strong className="font-semibold text-[#080809]">{compact(group.member_count)}</strong> members
                </div>
                <div className="mt-2 flex -space-x-1.5">
                  {members.map((u) => <div key={u.id} className="rounded-full ring-2 ring-white"><Avatar user={u} size={32} /></div>)}
                </div>
              </div>
              <div className="flex gap-2">
                {action}
                {group.viewer_is_member && <BlueBtn><I.plus className="h-4 w-4" /> Invite</BlueBtn>}
                <GrayBtn className="w-12 px-0"><I.chevron className="h-4 w-4" /></GrayBtn>
              </div>
            </div>
            {group.viewer_request_status === 'declined' && !group.viewer_is_member && (
              <div className="mb-3 rounded-md bg-[#fdecea] px-3 py-2 text-[13px] text-[#a1151c]">Your request to join was declined by the admins.</div>
            )}
            <div className="flex items-center justify-between border-t border-[#ced0d4]">
              <div className="flex overflow-x-auto">
                {['About', 'Discussion', 'Featured', 'People', 'Media', 'Files'].map((t) => {
                  const active = t === (group.can_read_feed ? 'Discussion' : 'About')
                  return (
                    <div key={t} className="relative px-4 py-4 text-[15px] font-semibold whitespace-nowrap" style={{ color: active ? BLUE : '#65686c' }}>
                      {t}
                      {active && <span className="absolute right-0 bottom-0 left-0 h-[3px] rounded-t" style={{ background: BLUE }} />}
                    </div>
                  )
                })}
              </div>
              <div className="hidden gap-2 sm:flex">
                <GrayBtn className="w-12 px-0"><I.search className="h-4 w-4" /></GrayBtn>
                <GrayBtn className="w-12 px-0"><I.dots className="h-4 w-4" /></GrayBtn>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1000px] gap-4 px-2 py-4 sm:px-4 lg:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-4">
          {group.can_read_feed ? (
            <>
              {group.viewer_is_member && <Composer me={me} viewer={viewer} placeholder="Write something..." />}
              <GroupFeed group={group} viewer={viewer} tick={tick} me={me} />
            </>
          ) : (
            <Card className="px-6 py-10 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#e4e6eb]">
                <PrivacyIcon p={group.privacy} className="h-7 w-7" />
              </div>
              <h3 className="mt-3 text-[20px] font-bold">This group is {group.privacy}</h3>
              <p className="mt-1 text-[15px] text-[#65686c]">Join this group to view or participate in discussions.</p>
            </Card>
          )}
        </div>
        <div className="space-y-4 lg:sticky lg:top-[90px] lg:h-fit">
          <Card className="p-4">
            <h3 className="text-[20px] font-bold">About</h3>
            <p className="mt-3 text-[15px]">{group.description}</p>
            <div className="mt-4 space-y-3 text-[15px]">
              <div className="flex gap-3">
                <PrivacyIcon p={group.privacy} className="mt-0.5 h-5 w-5 shrink-0 text-[#65686c]" />
                <div>
                  <div className="font-semibold">{group.privacy === 'public' ? 'Public' : group.privacy === 'private' ? 'Private' : 'Hidden'}</div>
                  <div className="text-[13px] text-[#65686c]">
                    {group.privacy === 'public' ? "Anyone can see who's in the group and what they post." : "Only members can see who's in the group and what they post."}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Avatar user={group.admin} size={20} />
                <div><span className="font-semibold">{group.admin.name}</span> <span className="text-[#65686c]">is an admin</span></div>
              </div>
            </div>
            {group.protected_space && (
              <div className="mt-4 flex gap-2 rounded-lg bg-[#ebf3ff] p-3 text-[13px] text-[#0a3a8a]">
                <I.shield className="h-4 w-4 shrink-0" /> Protected support space: Sentinel personas never enter.
              </div>
            )}
          </Card>
          {groups.filter((x) => x.id !== group.id).length > 0 && (
            <Card className="p-4">
              <h3 className="text-[17px] font-bold">Related groups</h3>
              {groups.filter((x) => x.id !== group.id).slice(0, 3).map((x) => (
                <button key={x.id} onClick={() => go(`/group/${x.id}`)} className="-mx-2 mt-2 flex w-[calc(100%+16px)] items-center gap-3 rounded-lg p-2 text-left hover:bg-[#f0f2f5]">
                  <GroupThumb group={x} size={48} />
                  <span className="min-w-0">
                    <span className="block truncate text-[15px] font-semibold">{x.name}</span>
                    <span className="block text-[13px] text-[#65686c]">{compact(x.member_count)} members</span>
                  </span>
                </button>
              ))}
            </Card>
          )}
        </div>
      </div>
      {joining && <JoinModal group={group} viewer={viewer} onClose={() => { setJoining(false); g.reload() }} />}
    </div>
  )
}

function JoinModal({ group, viewer, onClose }: { group: SbGroup; viewer: string; onClose: () => void }) {
  const [answers, setAnswers] = useState(group.join_questions.map(() => ''))
  const [result, setResult] = useState<string>()
  const submit = async () => {
    try {
      const r = await sandboxJoin(group.id, viewer, answers)
      setResult(r.status === 'approved' ? 'Approved! Welcome to the group.' : `Declined${r.note ? `: "${r.note}"` : ''}`)
    } catch (e) {
      setResult((e as Error).message)
    }
  }
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-[rgba(244,244,244,0.8)] p-4">
      <div className="w-full max-w-[500px] rounded-lg bg-white shadow-[0_12px_28px_rgba(0,0,0,0.2),0_2px_4px_rgba(0,0,0,0.1)]">
        <div className="relative border-b border-[#ced0d4] p-4 text-center">
          <h3 className="text-[20px] font-bold">Answer questions</h3>
          <button onClick={onClose} className="absolute top-3 right-4 flex h-9 w-9 items-center justify-center rounded-full bg-[#e4e6eb] hover:bg-[#d8dadf]" aria-label="Close">
            <I.close className="h-5 w-5 text-[#65686c]" />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-4">
          <div className="flex items-center gap-3">
            <GroupThumb group={group} size={40} />
            <p className="text-[15px]">Your request to join <strong>{group.name}</strong> will be reviewed by the admins. Answer their questions to help them.</p>
          </div>
          {group.join_questions.map((q, i) => (
            <label key={q} className="mt-4 block">
              <span className="text-[15px] font-semibold">{i + 1}. {q}</span>
              <textarea rows={2} className="mt-1.5 w-full resize-none rounded-md border border-[#ced0d4] px-3 py-2 text-[15px] outline-none focus:border-[#0866ff]" placeholder="Write an answer..."
                value={answers[i]} onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
            </label>
          ))}
          {result && <p className="mt-3 rounded-md bg-[#f0f2f5] p-3 text-[15px]">{result}</p>}
        </div>
        <div className="border-t border-[#ced0d4] p-4">
          {result ? <GrayBtn onClick={onClose} className="w-full">Done</GrayBtn> : <BlueBtn onClick={submit} className="w-full">Submit</BlueBtn>}
        </div>
      </div>
    </div>
  )
}

function GroupFeed({ group, viewer, tick, limit, showGroup, me }: { group: SbGroup; viewer: string; tick: number; limit?: number; showGroup?: boolean; me?: SbUser }) {
  const feed = useAsync(() => sandboxApi.feed(group.id, viewer), [group.id, viewer, tick])
  if (feed.error) return null
  return (
    <div className="space-y-4">
      {(feed.data ?? []).slice(0, limit).map((p) => <PostCard key={p.id} post={p} group={showGroup ? group : undefined} me={me} />)}
    </div>
  )
}

const Reactions = () => (
  <span className="flex -space-x-1">
    <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full ring-2 ring-white" style={{ background: 'linear-gradient(#18afff,#0062df)' }}>
      <I.like className="h-2.5 w-2.5 text-white" />
    </span>
    <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full text-[10px] text-white ring-2 ring-white" style={{ background: 'linear-gradient(#ff6680,#e61739)' }}>♥</span>
  </span>
)

function PostCard({ post, group, me }: { post: SbPost; group?: SbGroup; me?: SbUser }) {
  const [liked, setLiked] = useState(false)
  const likes = post.likes + (liked ? 1 : 0)
  return (
    <Card>
      <div className="flex items-start gap-2 px-4 pt-3">
        {group ? (
          <div className="relative h-10 w-10 shrink-0">
            <GroupThumb group={group} size={36} />
            <div className="absolute -right-0.5 -bottom-0.5 rounded-full ring-2 ring-white"><Avatar user={post.author} size={24} /></div>
          </div>
        ) : <Avatar user={post.author} />}
        <div className="min-w-0 flex-1">
          {group ? (
            <>
              <button onClick={() => go(`/group/${post.group_id}`)} className="block truncate text-[15px] font-semibold hover:underline">{group.name}</button>
              <div className="flex items-center gap-1 text-[13px] text-[#65686c]">
                <span className="font-semibold text-[#65686c]">{post.author.name}</span> · {timeAgo(post.created_at)} · <PrivacyIcon p={group.privacy} />
              </div>
            </>
          ) : (
            <>
              <div className="text-[15px] font-semibold">{post.author.name}</div>
              <div className="flex items-center gap-1 text-[13px] text-[#65686c]">
                {post.pinned && <><I.pin className="h-3 w-3" /> Pinned ·</>} <span title={post.id}>{timeAgo(post.created_at)}</span> · <I.globe className="h-3 w-3" />
              </div>
            </>
          )}
        </div>
        <button className="flex h-9 w-9 items-center justify-center rounded-full text-[#65686c] hover:bg-[#f0f2f5]" title={`Post ${post.id}`}><I.dots className="h-5 w-5" /></button>
      </div>
      <p className={`px-4 pt-2 pb-3 whitespace-pre-wrap ${!post.image && post.text.length < 90 ? 'text-[20px] leading-snug' : 'text-[15px]'}`}>{post.text}</p>
      {post.image && <img src={`/${post.image}`} alt={post.image_alt ?? ''} className="max-h-[560px] w-full bg-[#f0f2f5] object-contain" />}
      <div className="flex items-center justify-between px-4 py-2.5 text-[15px] text-[#65686c]">
        <span className="flex items-center gap-1.5">{likes > 0 && <><Reactions /> {likes}</>}</span>
        <span className="flex gap-3">
          {post.comments.length > 0 && <span className="hover:underline">{post.comments.length} comment{post.comments.length > 1 ? 's' : ''}</span>}
          {post.likes > 3 && <span>{Math.max(1, Math.floor(post.likes / 7))} shares</span>}
        </span>
      </div>
      <div className="mx-4 flex border-t border-[#ced0d4] py-1 text-[15px] font-semibold text-[#65686c]">
        <button onClick={() => setLiked(!liked)} className="flex flex-1 items-center justify-center gap-2 rounded-md py-1.5 hover:bg-[#f0f2f5]" style={liked ? { color: BLUE } : undefined}>
          <I.like className="h-5 w-5" /> Like
        </button>
        <button className="flex flex-1 items-center justify-center gap-2 rounded-md py-1.5 hover:bg-[#f0f2f5]"><I.comment className="h-5 w-5" /> Comment</button>
        <button className="flex flex-1 items-center justify-center gap-2 rounded-md py-1.5 hover:bg-[#f0f2f5]"><I.share className="h-5 w-5" /> Share</button>
      </div>
      <div className="space-y-2 border-t border-[#ced0d4] px-4 pt-2 pb-3">
        {post.comments.length > 1 && <div className="text-[15px] font-semibold text-[#65686c]">Most relevant <I.chevron className="inline h-3 w-3" /></div>}
        {post.comments.map((c) => (
          <div key={c.id} className="flex gap-1.5">
            <Avatar user={c.author} size={32} />
            <div className="min-w-0">
              <div className="inline-block rounded-[18px] bg-[#f0f2f5] px-3 py-2">
                <div className="text-[13px] font-semibold">{c.author.name}</div>
                <div className="text-[15px] leading-snug">{c.text}</div>
              </div>
              <div className="mt-0.5 flex gap-3 px-3 text-[12px] font-semibold text-[#65686c]">
                <span className="font-normal">{timeAgo(c.created_at)}</span><span>Like</span><span>Reply</span>
              </div>
            </div>
          </div>
        ))}
        <div className="flex items-center gap-1.5 pt-1">
          {me ? <Avatar user={me} size={32} /> : <div className="h-8 w-8 rounded-full bg-[#e4e6eb]" />}
          <div className="flex h-9 flex-1 items-center justify-between rounded-full bg-[#f0f2f5] px-3 text-[15px] text-[#65686c]">
            <span>Write a comment…</span>
            <span className="flex gap-2"><I.smile className="h-4 w-4" /><I.photo className="h-4 w-4" /></span>
          </div>
        </div>
      </div>
    </Card>
  )
}

function Messenger({ viewer, tick }: { viewer: string; tick: number }) {
  const threads = useAsync<SbThread[]>(() => sandboxApi.messages(viewer), [viewer, tick])
  const [sel, setSel] = useState<string>()
  const list = threads.data ?? []
  const active = list.find((t) => t.with.id === sel) ?? list[0]
  const endRef = useRef<HTMLDivElement>(null)
  const count = active?.messages.length
  useEffect(() => {
    // Scroll the thread only; scrollIntoView would also scroll an embedding page.
    endRef.current?.scrollTo({ top: endRef.current.scrollHeight })
  }, [active?.with.id, count])

  return (
    <div className="flex min-h-0 flex-1 bg-white">
      <div className="flex w-[84px] shrink-0 flex-col border-r border-[#e5e5e5] md:w-[360px]">
        <div className="hidden items-center justify-between px-4 pt-4 md:flex">
          <h2 className="text-[24px] font-bold">Chats</h2>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f0f2f5]"><I.dots className="h-5 w-5" /></div>
        </div>
        <div className="mx-4 mt-3 hidden h-9 items-center gap-2 rounded-full bg-[#f0f2f5] px-3 text-[15px] text-[#65686c] md:flex">
          <I.search className="h-4 w-4" /> Search Messenger
        </div>
        <div className="mt-2 hidden gap-2 px-4 md:flex">
          <span className="rounded-full bg-[#ebf5ff] px-3 py-1.5 text-[15px] font-semibold" style={{ color: BLUE }}>Inbox</span>
          <span className="rounded-full px-3 py-1.5 text-[15px] font-semibold text-[#080809] hover:bg-[#f0f2f5]">Communities</span>
        </div>
        <div className="mt-2 flex-1 overflow-y-auto px-2">
          {list.length === 0 && <p className="hidden px-3 py-4 text-[15px] text-[#65686c] md:block">No messages yet.</p>}
          {list.map((t, i) => {
            const last = t.messages[t.messages.length - 1]
            const isActive = active?.with.id === t.with.id
            return (
              <button key={t.with.id} onClick={() => setSel(t.with.id)}
                className={`flex w-full items-center gap-3 rounded-lg p-2 text-left ${isActive ? 'bg-[#ebf5ff]' : 'hover:bg-[#f0f2f5]'}`}>
                <Avatar user={t.with} size={56} online={i % 2 === 0} />
                <div className="hidden min-w-0 flex-1 md:block">
                  <div className="truncate text-[15px] font-medium">{t.with.name}</div>
                  <div className="flex text-[13px] text-[#65686c]">
                    <span className="truncate">{last?.outgoing ? 'You: ' : ''}{last?.text}</span>
                    {last && <span className="shrink-0">&nbsp;· {timeAgo(last.created_at)}</span>}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {active ? (
          <>
            <div className="flex h-16 items-center justify-between border-b border-[#e5e5e5] px-3 shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
              <div className="flex items-center gap-2">
                <Avatar user={active.with} size={40} online />
                <div>
                  <div className="text-[15px] font-semibold">{active.with.name}</div>
                  <div className="text-[13px] text-[#65686c]">Active now</div>
                </div>
              </div>
              <div className="flex gap-1" style={{ color: BLUE }}>
                {[I.phone, I.video, I.info].map((Ic, i) => <span key={i} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-[#f0f2f5]"><Ic className="h-5 w-5" /></span>)}
              </div>
            </div>
            <div ref={endRef} className="flex-1 overflow-y-auto px-4 py-4">
              <div className="mb-6 flex flex-col items-center text-center">
                <Avatar user={active.with} size={60} />
                <div className="mt-2 text-[17px] font-semibold">{active.with.name}</div>
                {active.with.bio && <div className="max-w-sm text-[13px] text-[#65686c]">{active.with.bio}</div>}
              </div>
              {active.messages.map((m, i) => {
                const prev = active.messages[i - 1]
                const next = active.messages[i + 1]
                const gap = !prev || new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() > 15 * 60 * 1000
                const firstOfRun = gap || prev?.outgoing !== m.outgoing
                const lastOfRun = !next || next.outgoing !== m.outgoing
                return (
                  <div key={m.id}>
                    {gap && <div className="my-3 text-center text-[12px] text-[#65686c]">{new Date(m.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</div>}
                    <div className={`flex items-end gap-2 ${m.outgoing ? 'justify-end' : 'justify-start'} ${firstOfRun ? 'mt-2' : 'mt-0.5'}`}>
                      {!m.outgoing && (lastOfRun ? <Avatar user={active.with} size={28} /> : <div className="w-7 shrink-0" />)}
                      <div className={`max-w-[70%] px-3 py-2 text-[15px] leading-snug ${m.outgoing ? 'text-white' : 'bg-[#f0f0f0]'}`}
                        style={{
                          background: m.outgoing ? BLUE : undefined,
                          borderRadius: m.outgoing
                            ? `18px ${firstOfRun ? 18 : 4}px ${lastOfRun ? 18 : 4}px 18px`
                            : `${firstOfRun ? 18 : 4}px 18px 18px ${lastOfRun ? 18 : 4}px`,
                        }}
                        title={new Date(m.created_at).toLocaleString()}>
                        {m.text}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center gap-2 px-3 py-3">
              <div className="flex gap-1" style={{ color: BLUE }}>
                <span className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-[#f0f2f5]"><I.plus className="h-5 w-5" /></span>
                <span className="hidden h-9 w-9 items-center justify-center rounded-full hover:bg-[#f0f2f5] sm:flex"><I.photo className="h-5 w-5" /></span>
              </div>
              <div className="flex h-9 flex-1 items-center justify-between rounded-full bg-[#f0f2f5] px-3 text-[15px] text-[#65686c]">
                <span className="truncate">{viewer === 'u_persona' ? 'Replies are drafted, checked by the Safety Governor and approved in Mission Control' : 'Aa'}</span>
                <I.smile className="h-5 w-5 shrink-0" style={{ color: BLUE }} />
              </div>
              <span className="flex h-9 w-9 items-center justify-center" style={{ color: BLUE }}><I.like className="h-5 w-5" /></span>
            </div>
          </>
        ) : (
          <div className="m-auto text-[15px] text-[#65686c]">Select a chat or start a new conversation</div>
        )}
      </div>
    </div>
  )
}

function Integrity({ tick }: { tick: number }) {
  const reports = useAsync<SbReport[]>(() => sandboxApi.reports(), [tick])
  const sevColor: Record<string, string> = { urgent: '#d03b3b', high: '#ec835a', normal: '#fab219', low: '#0ca30c' }
  return (
    <div className="mx-auto max-w-[680px] space-y-3">
      <Card className="flex items-center gap-3 p-4">
        <RoundIcon bg="#1b7a3d"><I.shield className="h-5 w-5" /></RoundIcon>
        <div>
          <h2 className="text-[20px] font-bold">Integrity inbox</h2>
          <p className="text-[15px] text-[#65686c]">Reports filed by Crime Sentinel missions after human approval.</p>
        </div>
      </Card>
      {reports.data?.length === 0 && <Card className="p-6 text-center text-[15px] text-[#65686c]">No reports yet.</Card>}
      {reports.data?.map((r) => (
        <Card key={r.id} className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded px-2 py-0.5 text-xs font-bold text-white" style={{ background: sevColor[r.severity] ?? '#77756f' }}>{r.severity.toUpperCase()}</span>
            <h3 className="text-[17px] font-semibold">{r.title}</h3>
            <span className="ml-auto text-[13px] text-[#65686c]">#{r.id} · {timeAgo(r.created_at)} · mission {r.mission_id}</span>
          </div>
          <p className="mt-2 text-[15px]">{r.body.executive_summary}</p>
          <p className="mt-2 text-[15px]"><strong>Recommended action:</strong> {r.body.recommended_action}</p>
          <details className="mt-2 text-[15px]">
            <summary className="cursor-pointer font-semibold" style={{ color: BLUE }}>Evidence ({r.body.evidence?.length ?? 0} posts)</summary>
            <ul className="mt-2 space-y-2">
              {r.body.evidence?.map((e: any) => (
                <li key={e.post_id} className="rounded-lg bg-[#f0f2f5] p-3">
                  <div className="text-[12px] text-[#65686c]">{e.post_id} · account {e.account_id} · {e.category} · {e.policy}</div>
                  <div>"{e.text}"</div>
                  {e.image_observation && <div className="text-[13px] text-[#65686c]">Image: {e.image_observation}</div>}
                </li>
              ))}
            </ul>
          </details>
        </Card>
      ))}
    </div>
  )
}
