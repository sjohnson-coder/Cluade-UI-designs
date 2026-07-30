//+------------------------------------------------------------------+
//|                                            GodModeTickGuard.mq5   |
//| V15.1.4 deterministic broker-side protection actuator.           |
//|                                                                  |
//| Python is the single protection-policy owner. While a fresh,      |
//| build-attested directive exists, this EA applies that exact       |
//| policy on every MT5 tick and does NOT run a competing BE/trail.   |
//| If the Python owner becomes stale, the local hard-floor, BE and   |
//| ATR trail remain available as a conservative fail-safe.           |
//+------------------------------------------------------------------+
#property copyright "GodMode"
#property version   "15.043"
#property strict

#include <Trade/Trade.mqh>

input long            MagicNumber          = 20250525;
input string          CommentPrefix        = "GODMODE_";
input ENUM_TIMEFRAMES ATRTimeframe         = PERIOD_M15;
input int             ATRPeriod            = 14;

input group           "Fallback break-even (only when Python owner is stale)"
input bool            EnableBreakEven      = true;
input double          BreakEvenAtR         = 0.8;
input double          BreakEvenBufferPts   = 10;

input group           "Fallback trailing stop (only when Python owner is stale)"
input bool            EnableTrailing       = true;
input double          TrailStartR          = 1.0;
input double          TrailATRMultiplier   = 1.2;

input group           "Fallback hard protective floor"
input bool            EnableHardFloor      = true;
input double          HardFloorR           = -1.0;

input group           "Python policy bridge"
input bool            EnableControlFile    = true;
input string          ControlFileName      = "godmode_control.csv";
input string          HeartbeatFileName    = "godmode_tickguard_heartbeat.csv";
input bool            ControlFileCommon    = false;
input int             ControlRefreshSecs   = 1;
input int             ControlHeartbeatSecs = 20;
input string          ExpectedEngineBuild  = "V15.4.3-READINESS-COMPONENT-KERNEL";

CTrade trade;
string g_atrSyms[];
int    g_atrHandles[];

ulong    g_ctrlTickets[];
string   g_ctrlDir[];                 // HOLD, CUT, PROTECT, RECOVER, BREATH
double   g_ctrlSL[];
datetime g_ctrlCreated[];
datetime g_ctrlExpiry[];
string   g_ctrlEngine[];
long     g_ctrlSequence[];
double   g_ctrlInitialRisk[];
double   g_ctrlEntry[];
double   g_ctrlProtectStartAtr[];
double   g_ctrlTrailStartAtr[];
double   g_ctrlMaxGiveback[];
double   g_ctrlMinLockFraction[];
double   g_ctrlAtr[];
double   g_ctrlMaxExtraR[];
bool     g_ctrlBrokerConfirmedProfit[];
string   g_activeEngine="";

int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   EventSetTimer(MathMax(1,ControlRefreshSecs));
   ReadControlFile();
   WriteHeartbeat();
   Print("GodModeTickGuard V15.4.3 active. Python policy owner / MT5 tick actuator.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int i=0;i<ArraySize(g_atrHandles);i++)
      if(g_atrHandles[i]!=INVALID_HANDLE) IndicatorRelease(g_atrHandles[i]);
}

void OnTimer()
{
   ReadControlFile();
   WriteHeartbeat();
   CleanupRiskGlobals();
}

void OnTick()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      string comment=PositionGetString(POSITION_COMMENT);
      if(!(magic==MagicNumber || StringFind(comment,CommentPrefix)==0)) continue;

      string sym=PositionGetString(POSITION_SYMBOL);
      bool isBuy=((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      double tp=PositionGetDouble(POSITION_TP);
      double cur=PositionGetDouble(POSITION_PRICE_CURRENT);
      double point=SymbolInfoDouble(sym,SYMBOL_POINT);
      int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      if(point<=0) point=_Point;

      int ci=ControlIndex(ticket);
      double suppliedRisk=(ci>=0 && ci<ArraySize(g_ctrlInitialRisk)) ? g_ctrlInitialRisk[ci] : 0.0;
      double risk=InitialRisk(ticket,entry,sl,sym,suppliedRisk);
      if(risk<=0) continue;
      double profitR=isBuy ? (cur-entry)/risk : (entry-cur)/risk;

      bool ctrlFresh=false;
      bool freshOwner=false;
      string directive="";
      if(EnableControlFile && ci>=0)
      {
         ctrlFresh=(g_ctrlExpiry[ci]>0 && TimeGMT() <= g_ctrlExpiry[ci] && g_ctrlCreated[ci]>0 && (TimeGMT()-g_ctrlCreated[ci])<=ControlHeartbeatSecs);
         directive=g_ctrlDir[ci];
         freshOwner=ctrlFresh && (directive=="HOLD" || directive=="CUT" || directive=="PROTECT" || directive=="RECOVER" || directive=="BREATH");
      }

      if(freshOwner && directive=="CUT")
      {
         if(!trade.PositionClose(ticket))
            Print("GodModeTickGuard CUT failed ticket=",ticket," retcode=",trade.ResultRetcode()," ",trade.ResultRetcodeDescription());
         continue;
      }

      double target=sl;
      bool targetRequested=false;
      bool allowLoosen=false;
      bool requireProfitable=false;

      if(freshOwner && (directive=="PROTECT" || directive=="RECOVER" || directive=="BREATH"))
      {
         double proposed=g_ctrlSL[ci];
         double policyAtr=g_ctrlAtr[ci];
         double profitDist=isBuy ? cur-entry : entry-cur;
         double profitAtr=(policyAtr>0) ? profitDist/policyAtr : -1.0;
         bool currentBrokerProfit=isBuy ? (sl>entry && sl<cur) : (sl<entry && sl>cur);
         bool proposedCorrectSide=isBuy ? (proposed<cur) : (proposed>cur);

         if(directive=="PROTECT")
         {
            bool thresholdMet=(policyAtr>0 && profitAtr>=g_ctrlProtectStartAtr[ci]) || currentBrokerProfit;
            bool proposedProfit=isBuy ? (proposed>entry && proposed<cur) : (proposed<entry && proposed>cur);
            bool improves=(sl<=0) || (isBuy ? proposed>sl : proposed<sl);
            if(proposed>0 && thresholdMet && proposedProfit && improves)
            {
               target=proposed; targetRequested=true; requireProfitable=true;
            }
            else Print("Rejected PROTECT ticket=",ticket," threshold=",thresholdMet," proposed=",DoubleToString(proposed,digits));
         }
         else if(directive=="BREATH")
         {
            bool proposedProfit=isBuy ? (proposed>entry && proposed<cur) : (proposed<entry && proposed>cur);
            bool brokerConfirmedProfit=g_ctrlBrokerConfirmedProfit[ci] && currentBrokerProfit;
            if(proposed>0 && brokerConfirmedProfit && proposedProfit)
            {
               target=proposed; targetRequested=true; allowLoosen=true; requireProfitable=true;
            }
            else Print("Rejected BREATH ticket=",ticket," brokerConfirmedProfit=",brokerConfirmedProfit);
         }
         else if(directive=="RECOVER")
         {
            double maxRisk=risk*(1.0+MathMax(0.0,g_ctrlMaxExtraR[ci]));
            double proposedRisk=MathAbs(entry-proposed);
            bool bounded=(proposedRisk<=maxRisk+point);
            bool protectiveSide=isBuy ? (proposed<entry && proposed<cur) : (proposed>entry && proposed>cur);
            if(proposed>0 && policyAtr>0 && bounded && protectiveSide && proposedCorrectSide)
            {
               target=proposed; targetRequested=true; allowLoosen=true;
            }
            else Print("Rejected RECOVER ticket=",ticket," atr=",policyAtr," proposedRisk=",proposedRisk," maxRisk=",maxRisk);
         }
      }

      // A fresh Python directive is authoritative. No competing local BE/trail is run.
      if(!freshOwner && EnableHardFloor && profitR<=HardFloorR)
      {
         if(!trade.PositionClose(ticket))
            Print("GodModeTickGuard fallback hard-floor failed ticket=",ticket," retcode=",trade.ResultRetcode());
         continue;
      }

      if(!freshOwner && EnableBreakEven && profitR>=BreakEvenAtR)
      {
         double be=isBuy ? entry+BreakEvenBufferPts*point : entry-BreakEvenBufferPts*point;
         target=TightenSL(target,be,isBuy);
         targetRequested=true;
         requireProfitable=true;
      }

      if(!freshOwner && EnableTrailing && profitR>=TrailStartR)
      {
         double atr=GetATR(sym);
         if(atr>0)
         {
            double trail=isBuy ? cur-atr*TrailATRMultiplier : cur+atr*TrailATRMultiplier;
            target=TightenSL(target,trail,isBuy);
            targetRequested=true;
            requireProfitable=true;
         }
      }

      if(!targetRequested || target<=0) continue;
      target=QuantizePrice(sym,target);
      double stopsLevel=(double)SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point;
      double freezeLevel=(double)SymbolInfoInteger(sym,SYMBOL_TRADE_FREEZE_LEVEL)*point;
      double minDistance=MathMax(stopsLevel,freezeLevel);
      if(isBuy && (cur-target)<minDistance) target=QuantizePrice(sym,cur-minDistance);
      if(!isBuy && (target-cur)<minDistance) target=QuantizePrice(sym,cur+minDistance);

      bool correctCurrentSide=isBuy ? target<cur : target>cur;
      bool profitable=isBuy ? target>entry : target<entry;
      bool improves=(sl<=0) || (isBuy ? target>sl : target<sl);
      if(!correctCurrentSide) target=sl;
      if(requireProfitable && !profitable) target=sl;
      if(!allowLoosen && !improves) target=sl;

      if(target>0 && MathAbs(target-sl)>point/2.0)
      {
         if(!trade.PositionModify(ticket,target,tp))
            Print("GodModeTickGuard modify failed ticket=",ticket," target=",DoubleToString(target,digits)," retcode=",trade.ResultRetcode()," ",trade.ResultRetcodeDescription());
         else if(PositionSelectByTicket(ticket) && MathAbs(PositionGetDouble(POSITION_SL)-target)>MathMax(SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE),point))
            Print("GodModeTickGuard modify readback mismatch ticket=",ticket," requested=",DoubleToString(target,digits)," actual=",DoubleToString(PositionGetDouble(POSITION_SL),digits));
      }
   }
}

double QuantizePrice(string sym,double price)
{
   double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   if(tick<=0) tick=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(tick<=0) return NormalizeDouble(price,digits);
   return NormalizeDouble(MathRound(price/tick)*tick,digits);
}

double TightenSL(double current,double candidate,bool isBuy)
{
   if(current<=0) return candidate;
   if(isBuy) return candidate>current ? candidate : current;
   return candidate<current ? candidate : current;
}

double InitialRisk(ulong ticket,double entry,double sl,string sym,double suppliedRisk)
{
   string gv=CommentPrefix+"RISK_"+(string)ticket;
   if(GlobalVariableCheck(gv))
   {
      double saved=GlobalVariableGet(gv);
      if(saved>0) return saved;
   }
   double risk=suppliedRisk>0 ? suppliedRisk : ((sl>0) ? MathAbs(entry-sl) : 0.0);
   // No arbitrary ATR fallback for owner directives. Fallback ATR is used only when
   // Python is stale and this EA is operating its conservative local fail-safe.
   if(risk<=0 && ControlIndex(ticket)<0) risk=GetATR(sym);
   if(risk>0) GlobalVariableSet(gv,risk);
   return risk;
}

void CleanupRiskGlobals()
{
   for(int i=GlobalVariablesTotal()-1;i>=0;i--)
   {
      string name=GlobalVariableName(i);
      if(StringFind(name,CommentPrefix+"RISK_")!=0) continue;
      string tkStr=StringSubstr(name,StringLen(CommentPrefix+"RISK_"));
      ulong tk=(ulong)StringToInteger(tkStr);
      if(!PositionSelectByTicket(tk)) GlobalVariableDel(name);
   }
}

void ResetSequenceGlobals()
{
   for(int i=GlobalVariablesTotal()-1;i>=0;i--)
   {
      string name=GlobalVariableName(i);
      if(StringFind(name,CommentPrefix+"SEQ_")==0) GlobalVariableDel(name);
   }
}

int GetATRHandle(string sym)
{
   for(int i=0;i<ArraySize(g_atrSyms);i++) if(g_atrSyms[i]==sym) return g_atrHandles[i];
   int handle=iATR(sym,ATRTimeframe,ATRPeriod);
   int n=ArraySize(g_atrSyms);
   ArrayResize(g_atrSyms,n+1); ArrayResize(g_atrHandles,n+1);
   g_atrSyms[n]=sym; g_atrHandles[n]=handle;
   return handle;
}

double GetATR(string sym)
{
   int handle=GetATRHandle(sym);
   if(handle==INVALID_HANDLE) return 0.0;
   double buffer[];
   if(CopyBuffer(handle,0,0,1,buffer)<1) return 0.0;
   return buffer[0];
}

int ControlIndex(ulong ticket)
{
   for(int i=0;i<ArraySize(g_ctrlTickets);i++) if(g_ctrlTickets[i]==ticket) return i;
   return -1;
}

void WriteHeartbeat()
{
   int flags=FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(ControlFileCommon) flags|=FILE_COMMON;
   int fh=FileOpen(HeartbeatFileName,flags);
   if(fh==INVALID_HANDLE) { Print("TickGuard heartbeat open failed error=",GetLastError()); return; }
   string payload=IntegerToString((long)TimeGMT())+","+ExpectedEngineBuild+","+IntegerToString(MagicNumber)+","+CommentPrefix+","+_Symbol;
   FileWriteString(fh,payload+"\n");
   FileFlush(fh); FileClose(fh);
}

void ResizeControlArrays(int size)
{
   ArrayResize(g_ctrlTickets,size); ArrayResize(g_ctrlDir,size); ArrayResize(g_ctrlSL,size);
   ArrayResize(g_ctrlCreated,size); ArrayResize(g_ctrlExpiry,size); ArrayResize(g_ctrlEngine,size);
   ArrayResize(g_ctrlSequence,size); ArrayResize(g_ctrlInitialRisk,size); ArrayResize(g_ctrlEntry,size);
   ArrayResize(g_ctrlProtectStartAtr,size); ArrayResize(g_ctrlTrailStartAtr,size);
   ArrayResize(g_ctrlMaxGiveback,size); ArrayResize(g_ctrlMinLockFraction,size); ArrayResize(g_ctrlAtr,size);
   ArrayResize(g_ctrlMaxExtraR,size); ArrayResize(g_ctrlBrokerConfirmedProfit,size);
}

void ReadControlFile()
{
   ResizeControlArrays(0);
   if(!EnableControlFile) return;
   int flags=FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(ControlFileCommon) flags|=FILE_COMMON;
   int fh=FileOpen(ControlFileName,flags);
   if(fh==INVALID_HANDLE) return;

   while(!FileIsEnding(fh))
   {
      string line=FileReadString(fh);
      if(StringLen(line)<3) continue;
      string parts[];
      int n=StringSplit(line,',',parts);
      if(n<8) continue;
      ulong tk=(ulong)StringToInteger(parts[0]);
      string dir=parts[1]; StringToUpper(dir);
      double slv=(n>=3) ? StringToDouble(parts[2]) : 0.0;
      datetime created=(n>=4) ? (datetime)StringToInteger(parts[3]) : 0;
      datetime expiry=(n>=5) ? (datetime)StringToInteger(parts[4]) : 0;
      string engine=(n>=6) ? parts[5] : "";
      long seq=(n>=7) ? StringToInteger(parts[6]) : 0;
      double initialRisk=(n>=8) ? StringToDouble(parts[7]) : 0.0;
      double entry=(n>=9) ? StringToDouble(parts[8]) : 0.0;
      double protectStartAtr=(n>=10) ? StringToDouble(parts[9]) : 0.55;
      double trailStartAtr=(n>=11) ? StringToDouble(parts[10]) : 0.75;
      double maxGiveback=(n>=12) ? StringToDouble(parts[11]) : 0.45;
      double minLockFraction=(n>=13) ? StringToDouble(parts[12]) : 0.30;
      double policyAtr=(n>=14) ? StringToDouble(parts[13]) : 0.0;
      double maxExtraR=(n>=15) ? StringToDouble(parts[14]) : 0.0;
      bool brokerConfirmedProfit=(n>=16 && StringToInteger(parts[15])==1);

      if(tk==0 || created<=0 || expiry<=created || TimeGMT()>expiry || (TimeGMT()-created)>ControlHeartbeatSecs) continue;
      if(StringLen(ExpectedEngineBuild)>0 && StringFind(engine,ExpectedEngineBuild)!=0) { Print("Rejected foreign engine directive ticket=",tk," engine=",engine); continue; }
      string seqKey=CommentPrefix+"SEQ_"+(string)tk;
      long lastSeq=GlobalVariableCheck(seqKey) ? (long)GlobalVariableGet(seqKey) : 0;
      if(g_activeEngine=="" || g_activeEngine!=engine)
      {
         g_activeEngine=engine; ResetSequenceGlobals(); GlobalVariableSet(seqKey,0.0); lastSeq=0;
      }
      if(seq<lastSeq) { Print("Rejected replayed directive ticket=",tk," seq=",seq," last=",lastSeq); continue; }
      GlobalVariableSet(seqKey,(double)seq);
      int m=ArraySize(g_ctrlTickets); ResizeControlArrays(m+1);
      g_ctrlTickets[m]=tk; g_ctrlDir[m]=dir; g_ctrlSL[m]=slv; g_ctrlCreated[m]=created; g_ctrlExpiry[m]=expiry;
      g_ctrlEngine[m]=engine; g_ctrlSequence[m]=seq; g_ctrlInitialRisk[m]=initialRisk; g_ctrlEntry[m]=entry;
      g_ctrlProtectStartAtr[m]=protectStartAtr; g_ctrlTrailStartAtr[m]=trailStartAtr;
      g_ctrlMaxGiveback[m]=maxGiveback; g_ctrlMinLockFraction[m]=minLockFraction; g_ctrlAtr[m]=policyAtr;
      g_ctrlMaxExtraR[m]=maxExtraR; g_ctrlBrokerConfirmedProfit[m]=brokerConfirmedProfit;
   }
   FileClose(fh);
}
//+------------------------------------------------------------------+
