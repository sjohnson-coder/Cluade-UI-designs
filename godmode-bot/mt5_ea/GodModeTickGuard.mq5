//+------------------------------------------------------------------+
//|                                            GodModeTickGuard.mq5   |
//|   Tick-level stop manager for GodMode Gold bot trades.           |
//|                                                                  |
//|   WHY: the Python bot manages on a ~3s poll loop (the MT5 Python |
//|   API is pull-based). This Expert Advisor runs INSIDE MT5 and    |
//|   reacts on EVERY tick (OnTick) to do the fast, safety-critical  |
//|   work sub-second: break-even, structure/ATR trailing, and a     |
//|   hard protective floor. The Python AI keeps doing the slow,     |
//|   intelligent work (entries, strategy, recovery verdict) and can |
//|   optionally steer this EA through a tiny control file:          |
//|     HOLD  -> the AI believes the trade will recover: this EA     |
//|              skips its hard floor so the trade is not cut early.  |
//|     CUT   -> the AI says it cannot recover: close on next tick.  |
//|                                                                  |
//|   It ONLY touches positions stamped with the GodMode magic       |
//|   number or comment prefix. Attach it to ONE XAUUSD chart.       |
//+------------------------------------------------------------------+
#property copyright "GodMode"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input long            MagicNumber          = 20250525;     // GodMode magic number (match the bot)
input string          CommentPrefix        = "GODMODE_";   // GodMode comment prefix (match the bot)
input ENUM_TIMEFRAMES ATRTimeframe         = PERIOD_M15;   // ATR timeframe for trailing
input int             ATRPeriod            = 14;           // ATR period

input group           "Break-even"
input bool            EnableBreakEven      = true;
input double          BreakEvenAtR         = 0.8;          // move SL to BE once profit >= this R
input double          BreakEvenBufferPts   = 10;           // points beyond entry when at BE

input group           "Trailing stop"
input bool            EnableTrailing       = true;
input double          TrailStartR          = 1.0;          // start trailing once profit >= this R
input double          TrailATRMultiplier   = 1.2;          // trail distance = ATR * this

input group           "Hard protective floor (sub-second cut)"
input bool            EnableHardFloor      = true;
input double          HardFloorR           = -1.0;         // close instantly if loss reaches this R

input group           "AI control bridge (optional)"
input bool            EnableControlFile    = true;         // read HOLD/CUT directives from the Python AI
input string          ControlFileName      = "godmode_control.csv";
input bool            ControlFileCommon    = false;        // true = read from the shared \Files\ (common) folder
input int             ControlRefreshSecs   = 1;            // how often to re-read the control file

CTrade  trade;

// ATR handle cache (per symbol)
string  g_atrSyms[];
int     g_atrHandles[];

// Control directives parsed from the file
ulong   g_ctrlTickets[];
string  g_ctrlDir[];      // "HOLD" or "CUT"
double  g_ctrlSL[];       // optional AI-suggested SL (0 = none)

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   EventSetTimer(MathMax(1, ControlRefreshSecs));
   ReadControlFile();
   Print("GodModeTickGuard active. Managing magic=", MagicNumber, " prefix=", CommentPrefix);
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
   CleanupRiskGlobals();
}

//+------------------------------------------------------------------+
//| Tick-level management — the whole point of this EA               |
//+------------------------------------------------------------------+
void OnTick()
{
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;

      long   magic   = PositionGetInteger(POSITION_MAGIC);
      string comment = PositionGetString(POSITION_COMMENT);
      if(!(magic==MagicNumber || StringFind(comment, CommentPrefix)==0)) continue; // not a GodMode trade

      string sym   = PositionGetString(POSITION_SYMBOL);
      bool   isBuy = ((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      double cur   = PositionGetDouble(POSITION_PRICE_CURRENT);
      double point = SymbolInfoDouble(sym, SYMBOL_POINT);
      int    digits= (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      if(point<=0) point = _Point;

      double risk = InitialRisk(ticket, entry, sl, sym);
      if(risk<=0) continue;
      double profitR = isBuy ? (cur-entry)/risk : (entry-cur)/risk;

      // ---- AI control directives -------------------------------------------
      int ci = ControlIndex(ticket);
      bool aiHold = false;
      if(EnableControlFile && ci>=0)
      {
         if(g_ctrlDir[ci]=="CUT")   { trade.PositionClose(ticket); continue; }
         if(g_ctrlDir[ci]=="HOLD")  aiHold = true;
      }

      // ---- Hard protective floor (instant) ---------------------------------
      // Skipped when the AI says HOLD (it judged the trade likely to recover and
      // owns a wider, risk-capped stop on the Python side).
      if(EnableHardFloor && !aiHold && profitR <= HardFloorR)
      {
         trade.PositionClose(ticket);
         continue;
      }

      // ---- Compute the protective SL target --------------------------------
      double target = sl;

      // Optional AI-suggested (risk-capped) SL — the only thing allowed to WIDEN.
      if(EnableControlFile && ci>=0 && g_ctrlSL[ci] > 0.0)
         target = g_ctrlSL[ci];

      // Break-even (tightens toward profit only)
      if(EnableBreakEven && profitR >= BreakEvenAtR)
      {
         double be = isBuy ? entry + BreakEvenBufferPts*point : entry - BreakEvenBufferPts*point;
         target = TightenSL(target, be, isBuy);
      }

      // ATR trailing (tightens toward profit only)
      if(EnableTrailing && profitR >= TrailStartR)
      {
         double atr = GetATR(sym);
         if(atr>0)
         {
            double trail = isBuy ? cur - atr*TrailATRMultiplier : cur + atr*TrailATRMultiplier;
            target = TightenSL(target, trail, isBuy);
         }
      }

      target = NormalizeDouble(target, digits);

      // Respect the broker's minimum stop distance to avoid rejects.
      double stopsLevel = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * point;
      if(target>0)
      {
         if(isBuy  && (cur - target) < stopsLevel) target = NormalizeDouble(cur - stopsLevel, digits);
         if(!isBuy && (target - cur) < stopsLevel) target = NormalizeDouble(cur + stopsLevel, digits);
      }

      if(target>0 && MathAbs(target - sl) > point/2.0)
         trade.PositionModify(ticket, target, tp);
   }
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
// Move a stop only in the protective direction (never widen via BE/trail).
double TightenSL(double current, double candidate, bool isBuy)
{
   if(current<=0) return candidate;
   if(isBuy)  return (candidate>current) ? candidate : current;
   return (candidate<current) ? candidate : current;
}

// Original risk (|entry - first SL|) persisted per ticket so R stays correct
// even after the stop is moved to break-even.
double InitialRisk(ulong ticket, double entry, double sl, string sym)
{
   string gv = CommentPrefix + "RISK_" + (string)ticket;
   if(GlobalVariableCheck(gv))
   {
      double v = GlobalVariableGet(gv);
      if(v>0) return v;
   }
   double r = (sl>0) ? MathAbs(entry-sl) : 0.0;
   if(r<=0) r = GetATR(sym);
   if(r>0)  GlobalVariableSet(gv, r);
   return r;
}

void CleanupRiskGlobals()
{
   int total = GlobalVariablesTotal();
   for(int i=total-1; i>=0; i--)
   {
      string name = GlobalVariableName(i);
      if(StringFind(name, CommentPrefix+"RISK_")!=0) continue;
      string tkStr = StringSubstr(name, StringLen(CommentPrefix+"RISK_"));
      ulong tk = (ulong)StringToInteger(tkStr);
      if(!PositionSelectByTicket(tk)) GlobalVariableDel(name); // position gone -> drop it
   }
}

int GetATRHandle(string sym)
{
   for(int i=0;i<ArraySize(g_atrSyms);i++)
      if(g_atrSyms[i]==sym) return g_atrHandles[i];
   int h = iATR(sym, ATRTimeframe, ATRPeriod);
   int n = ArraySize(g_atrSyms);
   ArrayResize(g_atrSyms, n+1); ArrayResize(g_atrHandles, n+1);
   g_atrSyms[n]=sym; g_atrHandles[n]=h;
   return h;
}

double GetATR(string sym)
{
   int h = GetATRHandle(sym);
   if(h==INVALID_HANDLE) return 0.0;
   double buf[];
   if(CopyBuffer(h, 0, 0, 1, buf) < 1) return 0.0;
   return buf[0];
}

int ControlIndex(ulong ticket)
{
   for(int i=0;i<ArraySize(g_ctrlTickets);i++)
      if(g_ctrlTickets[i]==ticket) return i;
   return -1;
}

// Parse the Python-written control file: lines of "ticket,DIRECTIVE[,sl]".
void ReadControlFile()
{
   ArrayResize(g_ctrlTickets, 0);
   ArrayResize(g_ctrlDir, 0);
   ArrayResize(g_ctrlSL, 0);
   if(!EnableControlFile) return;

   int flags = FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(ControlFileCommon) flags |= FILE_COMMON;
   int fh = FileOpen(ControlFileName, flags);
   if(fh==INVALID_HANDLE) return;

   while(!FileIsEnding(fh))
   {
      string line = FileReadString(fh);
      if(StringLen(line)<3) continue;
      string parts[];
      int n = StringSplit(line, ',', parts);
      if(n<2) continue;
      ulong  tk  = (ulong)StringToInteger(parts[0]);
      string dir = parts[1];
      StringToUpper(dir);
      double slv = (n>=3) ? StringToDouble(parts[2]) : 0.0;
      if(tk==0) continue;
      int m = ArraySize(g_ctrlTickets);
      ArrayResize(g_ctrlTickets, m+1); ArrayResize(g_ctrlDir, m+1); ArrayResize(g_ctrlSL, m+1);
      g_ctrlTickets[m]=tk; g_ctrlDir[m]=dir; g_ctrlSL[m]=slv;
   }
   FileClose(fh);
}
//+------------------------------------------------------------------+
