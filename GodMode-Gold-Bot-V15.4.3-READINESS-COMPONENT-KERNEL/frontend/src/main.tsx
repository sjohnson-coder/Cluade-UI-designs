window.addEventListener('error',(event)=>{console.error('[GodMode UI uncaught error]',event.error||event.message);try{window.dispatchEvent(new CustomEvent('godmode:ui-error',{detail:{path:'window.error',message:String(event.message||'UI error')}}));}catch{}});
window.addEventListener('unhandledrejection',(event)=>{console.error('[GodMode UI unhandled rejection]',event.reason);try{window.dispatchEvent(new CustomEvent('godmode:ui-error',{detail:{path:'unhandledrejection',message:String(event.reason||'Unhandled UI rejection')}}));}catch{}});
import React from 'react';import ReactDOM from 'react-dom/client';import './styles/theme.css';import App from './App';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
