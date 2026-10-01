import { lazy, Suspense, useEffect, useState } from 'react';
import { Activity, Bell, Bot, ChevronDown, ClipboardList, FileText, Globe2, LayoutDashboard, LogOut, Search, Shield, ShieldAlert, Siren, Target, Users, X } from 'lucide-react';
import { api, post } from './api';
import type { Session } from './types';
import AuthPage from './AuthPage';

const DashboardPage = lazy(() => import('./DashboardPage'));
const AssetsPage = lazy(() => import('./AssetsPage'));
const FindingsPage = lazy(() => import('./FindingsPage'));
const RisksPage = lazy(() => import('./RisksPage'));
const IncidentsPage = lazy(() => import('./IncidentsPage'));
const EventsPage = lazy(() => import('./EventsPage'));
const ReportsPage = lazy(() => import('./ReportsPage'));
const AnalystPage = lazy(() => import('./AnalystPage'));
const SettingsPage = lazy(() => import('./SettingsPage'));
const TeamPage = lazy(() => import('./TeamPage'));
const JoinPage = lazy(() => import('./JoinPage'));

type Page = 'dashboard'|'assets'|'findings'|'risks'|'incidents'|'events'|'reports'|'analyst'|'audit'|'settings'|'team';
const navGroups = [
  { title: { ar: 'مركز المتابعة', en: 'MONITOR' }, items: [
    { id: 'dashboard', ar: 'نظرة عامة', en: 'Overview', icon: LayoutDashboard },
    { id: 'assets', ar: 'الأصول والفحوص', en: 'Assets & scans', icon: Globe2 },
    { id: 'findings', ar: 'النتائج والثغرات', en: 'Findings', icon: ShieldAlert },
    { id: 'risks', ar: 'مركز المخاطر', en: 'Risk center', icon: Target },
  ] },
  { title: { ar: 'الاستجابة', en: 'RESPOND' }, items: [
    { id: 'incidents', ar: 'الحوادث', en: 'Incidents', icon: Siren },
    { id: 'events', ar: 'الأحداث الأمنية', en: 'Security events', icon: Activity },
    { id: 'reports', ar: 'التقارير', en: 'Reports', icon: FileText },
    { id: 'analyst', ar: 'المحلل الأمني', en: 'AI Analyst', icon: Bot },
  ] },
  { title: { ar: 'الإدارة', en: 'ADMIN' }, items: [
    { id: 'audit', ar: 'سجل التدقيق', en: 'Audit log', icon: ClipboardList },
    { id: 'team', ar: 'فريق المؤسسة', en: 'Organization team', icon: Users },
    { id: 'settings', ar: 'الجلسات والإعدادات', en: 'Sessions & settings', icon: Users },
  ] },
];

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<Page>('dashboard');
  const [en, setEn] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => { api<Session>('/auth/me').then(setSession).catch(() => setSession(null)).finally(() => setLoading(false)); }, []);
  useEffect(() => { document.documentElement.lang = en ? 'en' : 'ar'; document.documentElement.dir = en ? 'ltr' : 'rtl'; }, [en]);
  useEffect(() => {
    if (query.trim().length < 2) { setResults(null); return; }
    const timer = window.setTimeout(() => api(`/search?q=${encodeURIComponent(query.trim())}`).then(setResults).catch(e => setError(e.message)), 280);
    return () => window.clearTimeout(timer);
  }, [query]);

  async function authenticated() {
    setLoading(true);
    try { setSession(await api<Session>('/auth/me')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load session'); }
    finally { setLoading(false); }
  }
  async function logout() {
    try { await post('/auth/logout'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Logout failed'); }
    finally { setSession(null); }
  }

  if (loading) return <div className="boot-screen"><span className="boot-logo"><Shield size={22}/></span><span>CYBERSHIELD OS</span><i className="pulse-dot"/></div>;
  if (!session) return location.pathname === '/join'
    ? <Suspense fallback={<div className="boot-screen">…</div>}><JoinPage onAuth={authenticated} en={en}/></Suspense>
    : <AuthPage onAuth={authenticated} en={en}/>;

  const admin = ['ORGANIZATION_OWNER', 'SECURITY_ADMIN', 'IT_ADMIN'].includes(session.role);
  const pageLabels: Record<Page,string> = en
    ? { dashboard:'Overview',assets:'Assets & scans',findings:'Findings',risks:'Risk center',incidents:'Incidents',events:'Security events',reports:'Reports',analyst:'AI Analyst',audit:'Audit log',settings:'Sessions & settings',team:'Organization team' }
    : { dashboard:'نظرة عامة',assets:'الأصول والفحوص',findings:'النتائج والثغرات',risks:'مركز المخاطر',incidents:'الحوادث',events:'الأحداث الأمنية',reports:'التقارير',analyst:'المحلل الأمني',audit:'سجل التدقيق',settings:'الجلسات والإعدادات',team:'فريق المؤسسة' };
  const roleName: Record<string,string> = { ORGANIZATION_OWNER:en?'Owner':'مالك المؤسسة', SECURITY_ADMIN:en?'Security admin':'مسؤول أمن', SECURITY_ANALYST:en?'Analyst':'محلل أمن', IT_ADMIN:en?'IT admin':'مسؤول تقنية', EMPLOYEE:en?'Employee':'موظف', VIEWER:en?'Viewer':'مشاهد' };
  let content = null;
  switch (page) {
    case 'dashboard': content=<DashboardPage en={en}/>; break;
    case 'assets': content=<AssetsPage en={en}/>; break;
    case 'findings': content=<FindingsPage en={en}/>; break;
    case 'risks': content=<RisksPage en={en}/>; break;
    case 'incidents': content=<IncidentsPage en={en}/>; break;
    case 'events': content=<EventsPage en={en}/>; break;
    case 'reports': content=<ReportsPage en={en}/>; break;
    case 'analyst': content=<AnalystPage en={en}/>; break;
    case 'audit': content=<EventsPage en={en} audit/>; break;
    case 'team': content=<TeamPage en={en}/>; break;
    case 'settings': content=<SettingsPage en={en} session={session}/>; break;
  }
  return <div className={`app-shell ${en?'is-en':''}`}>
    <div className={`mobile-scrim ${mobileNav?'show':''}`} onClick={()=>setMobileNav(false)}/>
    <aside className={`sidebar ${mobileNav?'open':''}`}>
      <div className="sidebar-brand"><span className="brand-mark"><Shield size={20}/></span><div><b>CyberShield <em>OS</em></b><small>SECURITY OPERATIONS</small></div><button className="mobile-close" onClick={()=>setMobileNav(false)}><X size={18}/></button></div>
      <div className="org-switch"><span className="org-symbol">{session.organization?.name?.slice(0,1)||'C'}</span><div><b>{session.organization?.name||'Organization'}</b><small>{en?'Workspace':'مساحة عمل'}</small></div><ChevronDown size={14}/></div>
      <nav className="side-nav">{navGroups.map(group=><div className="nav-group" key={group.title.en}><span className="nav-group-title">{en?group.title.en:group.title.ar}</span>{group.items.filter(item=>admin||!['audit','team'].includes(item.id)).map(item=>{const id=item.id as Page;const Icon=item.icon;return <button key={item.id} className={`nav-link ${page===id?'active':''}`} onClick={()=>{setPage(id);setMobileNav(false);setResults(null)}}><Icon size={17}/><span>{en?item.en:item.ar}</span>{id==='findings'&&<i className="nav-dot"/>}</button>})}</div>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-safe"><span><Shield size={15}/></span><div><b>{en?'Scoped by authorization':'مقيد بالتفويض'}</b><small>{en?'No unapproved scans':'لا فحص دون موافقة'}</small></div></div><div className="profile-row"><span className="avatar">{session.user.full_name.slice(0,1)}</span><div><b>{session.user.full_name}</b><small>{roleName[session.role]||session.role}</small></div><button className="logout-btn" title={en?'Sign out':'تسجيل الخروج'} onClick={logout}><LogOut size={15}/></button></div></div>
    </aside>
    <main className="main-shell">
      <header className="topbar"><button className="mobile-menu" onClick={()=>setMobileNav(true)}><span/><span/><span/></button><div className="breadcrumb"><span>{en?'Workspace':'مساحة العمل'}</span><b>/</b><strong>{pageLabels[page]}</strong></div><div className="topbar-actions"><div className="global-search"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={en?'Search assets, findings, incidents…':'ابحث في الأصول والنتائج والحوادث…'}/>{query&&<button onClick={()=>{setQuery('');setResults(null)}}><X size={14}/></button>}{results&&<div className="search-results"><b>{en?'Search results':'نتائج البحث'}</b>{Object.entries(results).flatMap(([kind,list]:[string,any])=>list.map((x:any)=><button key={x.id} onClick={()=>{setPage(kind==='assets'?'assets':kind==='findings'?'findings':kind==='incidents'?'incidents':'reports');setResults(null);setQuery('')}}><small>{kind}</small><span>{x.name||x.title||x.hostname}</span></button>))}{Object.values(results).every((v:any)=>!v.length)&&<small>{en?'No matches':'لا توجد نتائج'}</small>}</div>}</div><button className="icon-button notification-button" title={en?'Notifications':'الإشعارات'}><Bell size={17}/><i/></button><button className="language-toggle" onClick={()=>setEn(!en)}><Globe2 size={15}/>{en?'AR':'EN'}</button></div></header>
      {error&&<button className="toast-error" onClick={()=>setError('')}>{error}<X size={15}/></button>}
      <Suspense fallback={<div className="loading">{en?'Loading module…':'جارٍ تحميل الوحدة…'}</div>}>{content}</Suspense>
    </main>
  </div>;
}
