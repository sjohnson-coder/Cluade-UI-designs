import { useEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import { pages } from './router';
import { ActionCenter } from './components/ActionCenter';
function getInitialPage(){return window.location.hash.replace('#/','')||'dashboard'}
export default function App(){const[page,setPage]=useState(getInitialPage());const Page=pages[page]||pages.dashboard;useEffect(()=>{const onHash=()=>setPage(getInitialPage());window.addEventListener('hashchange',onHash);return()=>window.removeEventListener('hashchange',onHash)},[]);const navigate=(next:string)=>{window.location.hash=`/${next}`;setPage(next)};return <AppShell current={page} onNavigate={navigate}><div key={page} className="page"><Page/><div className="footer-risk">The GodMode Gold Trading Bot is for educational purposes only. Trading involves risk.</div></div><ActionCenter/></AppShell>}
