//+------------------------------------------------------------------+
//|  XAUUSDSessionOverlay.mq5                                        |
//|                                                                  |
//|  Session-weighted gold exposure. Ports the one construction from |
//|  the accompanying study that survived transaction cost, an       |
//|  out-of-sample split, and a stale-print audit.                   |
//|                                                                  |
//|  Asia    18:05-02:00 NY : weight 1.5                             |
//|  London  02:00-08:00 NY : weight 0.5                             |
//|  NY      08:00-17:00 NY : weight 0.0                             |
//|                                                                  |
//|  The EA holds no directional view. It sizes a long-only gold     |
//|  position from the clock and from realised volatility. It will   |
//|  refuse to trade when the spread exceeds the measured edge --    |
//|  that guard is the difference between this being profitable and  |
//|  it being a slow donation to your broker.                        |
//+------------------------------------------------------------------+
#property copyright "XAUUSD structural research"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- exposure -------------------------------------------------------
input double InpAsiaWeight       = 1.5;    // 18:05-02:00 New York
input double InpLondonWeight     = 0.5;    // 02:00-08:00 New York
input double InpNewYorkWeight    = 0.0;    // 08:00-17:00 New York

//--- risk -----------------------------------------------------------
input double InpTargetVolAnnual  = 0.12;   // annualised vol the sizer aims at
input int    InpVolLookbackDays  = 20;
input double InpMaxLeverage      = 1.5;
input double InpRiskCapPct       = 2.0;    // hard per-session equity stop, %
input int    InpTrendFilterMA    = 200;    // 0 disables; else flat below the MA

//--- execution ------------------------------------------------------
input double InpMaxSpreadUSD     = 0.35;   // wider than this and the edge is gone
input double InpMinRebalanceLots = 0.02;   // ignore dust adjustments
input bool   InpFlatBeforeWeekend= true;   // no Friday-close gap exposure
input int    InpBrokerGMTOffset  = 2;      // broker server time offset from GMT
input ulong  InpMagic            = 20260901;

CTrade   trade;
int      maHandle = INVALID_HANDLE;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);

   if(InpTrendFilterMA > 0)
     {
      maHandle = iMA(_Symbol, PERIOD_D1, InpTrendFilterMA, 0, MODE_SMA, PRICE_CLOSE);
      if(maHandle == INVALID_HANDLE)
        {
         Print("failed to create MA handle");
         return INIT_FAILED;
        }
     }
   PrintFormat("SessionOverlay ready on %s. Asia %.2f / London %.2f / NY %.2f, max spread $%.2f",
               _Symbol, InpAsiaWeight, InpLondonWeight, InpNewYorkWeight, InpMaxSpreadUSD);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(maHandle != INVALID_HANDLE)
      IndicatorRelease(maHandle);
  }

//+------------------------------------------------------------------+
//| Broker server time -> New York wall clock.                       |
//| US DST: second Sunday of March to first Sunday of November.      |
//+------------------------------------------------------------------+
bool IsUSDaylightTime(const datetime gmt)
  {
   MqlDateTime t;
   TimeToStruct(gmt, t);
   if(t.mon < 3 || t.mon > 11) return false;
   if(t.mon > 3 && t.mon < 11) return true;

   // Date of the first Sunday in the current month, from any day in it.
   int first_sunday = ((t.day - t.day_of_week - 1 + 7) % 7) + 1;

   if(t.mon == 3)                                   // starts 2nd Sunday, 07:00 GMT
     {
      int second_sunday = first_sunday + 7;
      return t.day > second_sunday || (t.day == second_sunday && t.hour >= 7);
     }
   return t.day < first_sunday ||                   // ends 1st Sunday, 06:00 GMT
          (t.day == first_sunday && t.hour < 6);
  }

void NewYorkNow(int &hour, int &minute, int &weekday)
  {
   datetime gmt = TimeCurrent() - InpBrokerGMTOffset * 3600;
   datetime ny  = gmt - (IsUSDaylightTime(gmt) ? 4 : 5) * 3600;
   MqlDateTime t;
   TimeToStruct(ny, t);
   hour = t.hour; minute = t.min; weekday = t.day_of_week;
  }

//+------------------------------------------------------------------+
double SessionWeight()
  {
   int hour, minute, weekday;
   NewYorkNow(hour, minute, weekday);
   int mins = hour * 60 + minute;

   if(weekday == 0 || weekday == 6) return 0.0;                 // weekend
   if(InpFlatBeforeWeekend && weekday == 5 && mins >= 15 * 60) return 0.0;

   if(mins >= 18 * 60 + 5 || mins < 2 * 60) return InpAsiaWeight;
   if(mins >= 2 * 60  && mins < 8 * 60)     return InpLondonWeight;
   if(mins >= 8 * 60  && mins < 17 * 60)    return InpNewYorkWeight;
   return 0.0;                                                   // 17:00-18:05 rollover
  }

//+------------------------------------------------------------------+
//| Annualised realised volatility from daily closes.                |
//+------------------------------------------------------------------+
double RealisedVol()
  {
   int need = InpVolLookbackDays + 1;
   double closes[];
   if(CopyClose(_Symbol, PERIOD_D1, 0, need, closes) < need) return 0.0;

   double sum = 0.0, rets[];
   ArrayResize(rets, need - 1);
   for(int i = 1; i < need; i++)
     {
      rets[i - 1] = closes[i] / closes[i - 1] - 1.0;
      sum += rets[i - 1];
     }
   double mean = sum / (need - 1), var = 0.0;
   for(int i = 0; i < need - 1; i++)
      var += MathPow(rets[i] - mean, 2);
   var /= (need - 2);
   return MathSqrt(var) * MathSqrt(252.0);
  }

double VolScalar()
  {
   double vol = RealisedVol();
   if(vol <= 0.0) return 1.0;
   return MathMin(InpTargetVolAnnual / vol, InpMaxLeverage);
  }

bool TrendOK()
  {
   if(InpTrendFilterMA <= 0 || maHandle == INVALID_HANDLE) return true;
   double ma[], close[];
   if(CopyBuffer(maHandle, 0, 0, 1, ma) < 1) return true;
   if(CopyClose(_Symbol, PERIOD_D1, 0, 1, close) < 1) return true;
   return close[0] > ma[0];
  }

//+------------------------------------------------------------------+
double CurrentSpreadUSD()
  {
   return SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
  }

double NetPositionLots()
  {
   double lots = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      lots += (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? v : -v;
     }
   return lots;
  }

double NormaliseLots(double lots)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lo   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double hi   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < lo) return 0.0;
   return MathMin(lots, hi);
  }

//+------------------------------------------------------------------+
double TargetLots()
  {
   double weight = SessionWeight();
   if(weight <= 0.0 || !TrendOK()) return 0.0;

   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(price <= 0.0) return 0.0;

   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 100.0;                  // XAUUSD: 100 oz / lot

   double notional = AccountInfoDouble(ACCOUNT_EQUITY) * weight * VolScalar();
   return NormaliseLots(notional / (price * contract));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime barTime = iTime(_Symbol, PERIOD_M5, 0);
   if(barTime == lastBarTime) return;                     // act once per M5 bar
   lastBarTime = barTime;

   // Per-session equity stop. Checked before anything else.
   double open_pl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         open_pl += PositionGetDouble(POSITION_PROFIT);
     }
   double cap = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskCapPct / 100.0;
   if(open_pl < -cap)
     {
      PrintFormat("session loss %.2f breached cap %.2f -- flattening", open_pl, cap);
      ClosePosition();
      return;
     }

   double spread = CurrentSpreadUSD();
   double current = NetPositionLots();
   double target  = TargetLots();
   double delta   = target - current;

   if(MathAbs(delta) < InpMinRebalanceLots) return;

   // Widening spreads at the rollover are exactly where a naive version of this
   // strategy gives back its edge. Only pay up to flatten risk, never to add.
   if(spread > InpMaxSpreadUSD && MathAbs(target) > MathAbs(current))
     {
      PrintFormat("spread $%.2f > $%.2f -- deferring increase to %.2f lots",
                  spread, InpMaxSpreadUSD, target);
      return;
     }

   if(delta > 0) trade.Buy(NormaliseLots(delta), _Symbol, 0, 0, 0, "overlay+");
   else          trade.Sell(NormaliseLots(-delta), _Symbol, 0, 0, 0, "overlay-");
  }

//+------------------------------------------------------------------+
void ClosePosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         trade.PositionClose(ticket);
     }
  }
//+------------------------------------------------------------------+
