import { useEffect, useState } from 'react';
import { Crown, LogIn, LogOut, Save } from 'lucide-react';
import { Card, PageHeader, SectionTitle, Tag } from '../components/ui';

type User={name:string;email:string;plan:string};
function loadUser():User{return {name:'Alex Trader',email:'',plan:'Premium Pro',...JSON.parse(localStorage.getItem('godmode_user')||'{}')}}
export default function Login(){
  const [user,setUser]=useState<User>(loadUser());
  const [saved,setSaved]=useState(false);
  useEffect(()=>{setUser(loadUser())},[]);
  const save=()=>{localStorage.setItem('godmode_user',JSON.stringify(user)); setSaved(true); setTimeout(()=>setSaved(false),2500); window.dispatchEvent(new StorageEvent('storage',{key:'godmode_user'}));};
  const logout=()=>{localStorage.removeItem('godmode_user'); setUser({name:'Alex Trader',email:'',plan:'Premium Pro'}); window.dispatchEvent(new StorageEvent('storage',{key:'godmode_user'}));};
  return <>
    <PageHeader title="Profile & Login" subtitle="Local user profile for this trading terminal. Broker authentication remains inside MT5 settings." right={saved?<Tag color="green">Saved</Tag>:<Tag color="gold">Local terminal profile</Tag>}/>
    <div className="login-page"><Card className="modal-card"><SectionTitle icon={<Crown size={22}/>} title="GodMode Trader Profile" right={<Tag color="gold">Secure local</Tag>}/><p className="muted">This profile controls the dashboard display name and plan badge. It does not store MT5 broker credentials; those remain in Settings → MT5 Connection.</p><label className="form-row"><span>Name</span><input className="input" value={user.name} onChange={e=>setUser({...user,name:e.target.value})}/></label><label className="form-row"><span>Email</span><input className="input" value={user.email} onChange={e=>setUser({...user,email:e.target.value})} placeholder="optional"/></label><label className="form-row"><span>Plan Badge</span><select className="input" value={user.plan} onChange={e=>setUser({...user,plan:e.target.value})}><option>Premium Pro</option><option>Live Mode</option><option>Demo Mode</option><option>GodMode Elite</option></select></label><div className="button-wrap" style={{marginTop:16}}><button className="gold-button" onClick={save}><Save size={14}/> Save Profile</button><button className="outline-button" onClick={logout}><LogOut size={14}/> Reset</button><button className="ghost-button" onClick={()=>{window.location.hash='/dashboard'}}><LogIn size={14}/> Back to Dashboard</button></div></Card></div>
  </>
}
