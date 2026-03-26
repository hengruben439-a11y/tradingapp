//+------------------------------------------------------------------+
//|                                                  made_EA_MT5.mq5 |
//|                           made. — Intelligent Signal Platform    |
//|                                          https://made.app        |
//|                                                                  |
//| MQL5 port of the made. EA. Uses CTrade, CPositionInfo, and       |
//| COrderInfo classes from the MQL5 standard library.               |
//| Same polling and TP-management logic as the MT4 version,         |
//| adapted for MQL5 execution model and class-based API.            |
//|                                                                  |
//| Installation:                                                    |
//|   1. Copy to MQL5/Experts/                                       |
//|   2. Compile in MetaEditor                                       |
//|   3. Attach to XAUUSD or GBPJPY chart                           |
//|   4. Enable AutoTrading                                          |
//|   5. Allow WebRequest: Tools > Options > Expert Advisors >       |
//|      "Allow WebRequest" > add http://localhost:8000              |
//+------------------------------------------------------------------+

#property copyright "made. — Intelligent Signal Platform"
#property link      "https://made.app"
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>
#include <Trade\HistoryOrderInfo.mqh>

//---- Input parameters --------------------------------------------------------

input string   BackendURL      = "http://localhost:8000";  // made. backend URL
input ulong    MagicNumber     = 20260101;                 // Unique EA identifier
input double   MaxSlippagePips = 2.0;                      // Max price deviation from signal entry
input bool     EnableTrading   = true;                     // Master kill switch
input bool     EnableLogging   = true;                     // Verbose console logging
input string   EASecret        = "ea-dev-secret";          // Shared secret for X-EA-Secret header
input int      PollIntervalSec = 5;                        // How often to poll for new signals

//---- Objects -----------------------------------------------------------------

CTrade         trade;
CPositionInfo  posInfo;
COrderInfo     orderInfo;

//---- State -------------------------------------------------------------------

string processedSignalIds[];
int    processedCount = 0;
datetime lastBarTime  = 0;

//+------------------------------------------------------------------+
//| Expert initialisation                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints((ulong)MathCeil(MaxSlippagePips * 10));
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   if (!EnableTrading)
      Print("[made.] Trading disabled — monitor-only mode.");

   // Validate WebRequest is permitted
   char   postData[];
   char   result[];
   string responseHeaders;
   string url = BackendURL + "/health";
   int res = WebRequest("GET", url, "", 5000, postData, result, responseHeaders);

   if (res == -1)
   {
      int err = GetLastError();
      if (err == 4014)
      {
         Alert("[made.] WebRequest blocked for: " + BackendURL +
               "\nAdd it under Tools > Options > Expert Advisors > Allow WebRequest.");
         return INIT_FAILED;
      }
      if (EnableLogging)
         Print("[made.] Backend not yet reachable (will retry on timer): err=", err);
   }
   else
   {
      if (EnableLogging)
         Print("[made.] Backend OK. EA ready. Magic=", MagicNumber);
   }

   EventSetTimer(PollIntervalSec);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if (EnableLogging)
      Print("[made.] EA removed. Reason=", reason);
}

//+------------------------------------------------------------------+
//| OnTimer — poll backend for new pending signals                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   if (!EnableTrading)
      return;

   string url = BackendURL + "/broker/ea/pending?magic=" + IntegerToString(MagicNumber);
   string body = HttpGet(url);

   if (StringLen(body) == 0)
      return;

   ProcessPendingSignals(body);
}

//+------------------------------------------------------------------+
//| OnTick — manage open positions                                   |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime currentBar = iTime(_Symbol, Period(), 0);
   if (currentBar == lastBarTime)
      return;
   lastBarTime = currentBar;

   ManageOpenPositions();
}

//+------------------------------------------------------------------+
//| OnTrade — called after trade events (fills, modifications, etc.) |
//+------------------------------------------------------------------+
void OnTrade()
{
   // Check for newly closed positions (SL hits) by inspecting history
   HistorySelect(TimeCurrent() - 3600, TimeCurrent());

   int dealsTotal = HistoryDealsTotal();
   for (int i = dealsTotal - 1; i >= 0; i--)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if (dealTicket <= 0)
         continue;
      if ((ulong)HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != MagicNumber)
         continue;
      if (HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol)
         continue;

      // DEAL_ENTRY_OUT = position close
      if (HistoryDealGetInteger(dealTicket, DEAL_ENTRY) == DEAL_ENTRY_OUT)
      {
         // Check reason: if reason is DEAL_REASON_SL, report SL hit
         if (HistoryDealGetInteger(dealTicket, DEAL_REASON) == DEAL_REASON_SL)
         {
            long positionId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
            double closePrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
            double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
            ReportSLHit((int)positionId, closePrice, profit);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ProcessPendingSignals — parse JSON array and execute each signal |
//+------------------------------------------------------------------+
void ProcessPendingSignals(string jsonArray)
{
   int pos = 0;
   int len = StringLen(jsonArray);

   while (pos < len)
   {
      int objStart = StringFind(jsonArray, "{", pos);
      if (objStart == -1) break;

      int objEnd = FindJsonObjectEnd(jsonArray, objStart);
      if (objEnd == -1) break;

      string signalJson = StringSubstr(jsonArray, objStart, objEnd - objStart + 1);
      ExecuteSignal(signalJson);

      pos = objEnd + 1;
   }
}

//+------------------------------------------------------------------+
//| ExecuteSignal — validate and open a position for one signal      |
//+------------------------------------------------------------------+
void ExecuteSignal(string json)
{
   string signalId   = JsonExtractString(json, "signal_id");
   string pair       = JsonExtractString(json, "pair");
   string direction  = JsonExtractString(json, "direction");
   double entryPrice = JsonExtractDouble(json, "entry_price");
   double sl         = JsonExtractDouble(json, "sl");
   double tp1        = JsonExtractDouble(json, "tp1");
   double tp2        = JsonExtractDouble(json, "tp2");
   double tp3        = JsonExtractDouble(json, "tp3");
   double lots       = JsonExtractDouble(json, "lot_size");

   if (StringLen(signalId) == 0 || StringLen(direction) == 0 || entryPrice <= 0)
   {
      if (EnableLogging)
         Print("[made.] Skipping malformed signal: ", json);
      return;
   }

   if (IsAlreadyProcessed(signalId))
   {
      if (EnableLogging)
         Print("[made.] Signal already processed: ", signalId);
      return;
   }

   if (pair != _Symbol)
   {
      if (EnableLogging)
         Print("[made.] Signal pair ", pair, " != chart symbol ", _Symbol, " — skipping.");
      return;
   }

   // Slippage validation
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double pipSize = (digits == 3 || digits == 5) ? point * 10.0 : point;

   double currentPrice = (direction == "BUY")
      ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
      : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double deviation = MathAbs(currentPrice - entryPrice);
   double tolerance = MaxSlippagePips * pipSize;

   if (deviation > tolerance)
   {
      if (EnableLogging)
         Print("[made.] Signal ", signalId, " REJECTED — deviation=",
               DoubleToString(deviation, digits), " > tolerance=",
               DoubleToString(tolerance, digits));
      ConfirmExecution(signalId, 0, 0, 0, "rejected", "price_deviation");
      MarkProcessed(signalId);
      return;
   }

   // Normalise lots
   if (lots <= 0) lots = 0.01;
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lotMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathMax(lotMin, MathMin(lotMax, MathRound(lots / lotStep) * lotStep));
   lots = NormalizeDouble(lots, 2);

   bool ok = false;
   if (direction == "BUY")
      ok = trade.Buy(lots, _Symbol, currentPrice, sl, tp1, "made." + signalId);
   else
      ok = trade.Sell(lots, _Symbol, currentPrice, sl, tp1, "made." + signalId);

   if (!ok)
   {
      uint err = trade.ResultRetcode();
      if (EnableLogging)
         Print("[made.] Trade FAILED for signal ", signalId,
               " retcode=", err, " comment=", trade.ResultComment());
      ConfirmExecution(signalId, 0, 0, (int)err, "failed",
                       "order_error_" + IntegerToString(err));
   }
   else
   {
      ulong  posTicket  = trade.ResultOrder();
      double fillPrice  = trade.ResultPrice();

      // Store TP2/TP3 in global variables keyed by position ticket
      GlobalVariableSet("made_tp2_"  + IntegerToString(posTicket), tp2);
      GlobalVariableSet("made_tp3_"  + IntegerToString(posTicket), tp3);
      GlobalVariableSet("made_tp1_"  + IntegerToString(posTicket), tp1);
      GlobalVariableSet("made_ent_"  + IntegerToString(posTicket), entryPrice);

      if (EnableLogging)
         Print("[made.] Position opened. Ticket=", posTicket,
               " Signal=", signalId,
               " Fill=", DoubleToString(fillPrice, digits),
               " Entry=", DoubleToString(entryPrice, digits));

      ConfirmExecution(signalId, (int)posTicket, fillPrice, 0, "filled", "");
   }

   MarkProcessed(signalId);
}

//+------------------------------------------------------------------+
//| ManageOpenPositions — partial closes and SL trailing             |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   int total = PositionsTotal();
   for (int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if (ticket == 0) continue;
      if (!posInfo.SelectByTicket(ticket)) continue;
      if (posInfo.Magic() != MagicNumber) continue;
      if (posInfo.Symbol() != _Symbol) continue;

      double tp2 = GlobalVariableGet("made_tp2_" + IntegerToString(ticket));
      double tp3 = GlobalVariableGet("made_tp3_" + IntegerToString(ticket));
      double tp1 = GlobalVariableGet("made_tp1_" + IntegerToString(ticket));
      double entryPrice = GlobalVariableGet("made_ent_" + IntegerToString(ticket));

      if (tp2 <= 0 || tp3 <= 0) continue;

      ENUM_POSITION_TYPE posType = posInfo.PositionType();
      double currentPrice = (posType == POSITION_TYPE_BUY)
         ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
         : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      double currentTP = posInfo.TakeProfit();
      double lots      = posInfo.Volume();
      double sl        = posInfo.StopLoss();

      bool tp1Hit = (posType == POSITION_TYPE_BUY)
         ? (currentPrice >= currentTP && currentTP > 0)
         : (currentPrice <= currentTP && currentTP > 0);
      bool tp2Hit = (posType == POSITION_TYPE_BUY)
         ? (currentPrice >= tp2)
         : (currentPrice <= tp2);

      // TP1 reached — close 40%, move SL to entry
      if (tp1Hit && !IsTP1Managed((int)ticket))
      {
         double closeQty = NormalizeDouble(lots * 0.40, 2);
         double lotStep  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
         double lotMin   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         closeQty = MathMax(lotMin, MathRound(closeQty / lotStep) * lotStep);

         if (closeQty <= lots)
         {
            double closePrice = (posType == POSITION_TYPE_BUY)
               ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
               : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

            if (trade.PositionClosePartial(ticket, closeQty))
            {
               // Move SL to entry (breakeven)
               trade.PositionModify(ticket, entryPrice, tp2);
               SetTP1Managed((int)ticket);
               ReportTPHit((int)ticket, 1, closePrice);

               if (EnableLogging)
                  Print("[made.] TP1 hit. Ticket=", ticket,
                        " Closed=", DoubleToStr(closeQty, 2), " lots",
                        " SL → entry=", DoubleToStr(entryPrice, Digits()));
            }
         }
      }

      // TP2 reached — close 50% of remaining, trail SL to TP1
      if (tp2Hit && IsTP1Managed((int)ticket) && !IsTP2Managed((int)ticket))
      {
         if (!posInfo.SelectByTicket(ticket)) continue;
         double remainingLots = posInfo.Volume();
         double closeQty = NormalizeDouble(remainingLots * 0.50, 2);
         double lotStep  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
         double lotMin   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         closeQty = MathMax(lotMin, MathRound(closeQty / lotStep) * lotStep);

         if (closeQty <= remainingLots)
         {
            double closePrice = (posType == POSITION_TYPE_BUY)
               ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
               : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

            if (trade.PositionClosePartial(ticket, closeQty))
            {
               // Trail SL to TP1 level
               double newSL = (tp1 > 0) ? tp1 : entryPrice;
               trade.PositionModify(ticket, newSL, tp3);
               SetTP2Managed((int)ticket);
               ReportTPHit((int)ticket, 2, closePrice);

               if (EnableLogging)
                  Print("[made.] TP2 hit. Ticket=", ticket,
                        " Closed=", DoubleToStr(closeQty, 2), " lots",
                        " SL → TP1=", DoubleToStr(newSL, Digits()));
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ConfirmExecution — POST fill details to backend                  |
//+------------------------------------------------------------------+
void ConfirmExecution(string signalId, int ticket, double fillPrice,
                      int errorCode, string status, string reason)
{
   string url  = BackendURL + "/broker/ea/confirm";
   string body = "{\"signal_id\":\"" + signalId + "\"," +
                 "\"ticket\":"       + IntegerToString(ticket)    + "," +
                 "\"fill_price\":"   + DoubleToString(fillPrice, Digits()) + "," +
                 "\"status\":\""     + status                      + "\"," +
                 "\"reason\":\""     + reason                      + "\"," +
                 "\"error_code\":"   + IntegerToString(errorCode)  + "," +
                 "\"magic\":"        + IntegerToString(MagicNumber) + "}";
   HttpPost(url, body);
}

//+------------------------------------------------------------------+
//| ReportTPHit — POST TP level hit to backend                       |
//+------------------------------------------------------------------+
void ReportTPHit(int ticket, int tpLevel, double hitPrice)
{
   string url  = BackendURL + "/broker/ea/tp_hit";
   string body = "{\"ticket\":"    + IntegerToString(ticket)       + "," +
                 "\"tp_level\":"   + IntegerToString(tpLevel)      + "," +
                 "\"hit_price\":"  + DoubleToString(hitPrice, Digits()) + "," +
                 "\"magic\":"      + IntegerToString(MagicNumber)  + "," +
                 "\"symbol\":\""   + _Symbol                        + "\"}";
   HttpPost(url, body);
}

//+------------------------------------------------------------------+
//| ReportSLHit — POST SL hit to backend (triggers post-mortem)      |
//+------------------------------------------------------------------+
void ReportSLHit(int ticket, double closePrice, double profit)
{
   string url  = BackendURL + "/broker/ea/sl_hit";
   string body = "{\"ticket\":"      + IntegerToString(ticket)      + "," +
                 "\"close_price\":"  + DoubleToString(closePrice, Digits()) + "," +
                 "\"profit_usd\":"   + DoubleToString(profit, 2)    + "," +
                 "\"magic\":"        + IntegerToString(MagicNumber) + "," +
                 "\"symbol\":\""     + _Symbol                       + "\"}";
   HttpPost(url, body);
}

//+------------------------------------------------------------------+
//| HttpGet — GET request, returns response body                     |
//+------------------------------------------------------------------+
string HttpGet(string url)
{
   char   postData[];
   char   result[];
   string responseHeaders;
   string reqHeaders = "X-EA-Secret: " + EASecret + "\r\n" +
                       "Content-Type: application/json\r\n";

   int res = WebRequest("GET", url, reqHeaders, 5000, postData, result, responseHeaders);
   if (res == -1)
   {
      int err = GetLastError();
      if (err != 5 && EnableLogging)
         Print("[made.] GET failed. URL=", url, " err=", err);
      return "";
   }
   return CharArrayToString(result);
}

//+------------------------------------------------------------------+
//| HttpPost — POST JSON body, returns true on success               |
//+------------------------------------------------------------------+
bool HttpPost(string url, string jsonBody)
{
   uchar  postData[];
   uchar  result[];
   string responseHeaders;
   string reqHeaders = "X-EA-Secret: " + EASecret + "\r\n" +
                       "Content-Type: application/json\r\n";

   StringToCharArray(jsonBody, postData, 0, StringLen(jsonBody));

   int res = WebRequest("POST", url, reqHeaders, 5000, postData, result, responseHeaders);
   if (res == -1)
   {
      int err = GetLastError();
      if (EnableLogging)
         Print("[made.] POST failed. URL=", url, " err=", err);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Processed signal ID deduplication                                |
//+------------------------------------------------------------------+
bool IsAlreadyProcessed(string signalId)
{
   for (int i = 0; i < processedCount; i++)
      if (processedSignalIds[i] == signalId)
         return true;
   return false;
}

void MarkProcessed(string signalId)
{
   ArrayResize(processedSignalIds, processedCount + 1);
   processedSignalIds[processedCount] = signalId;
   processedCount++;

   if (processedCount > 200)
   {
      for (int i = 0; i < processedCount - 100; i++)
         processedSignalIds[i] = processedSignalIds[i + 100];
      processedCount -= 100;
      ArrayResize(processedSignalIds, processedCount);
   }
}

//+------------------------------------------------------------------+
//| TP management state (GlobalVariable-backed)                      |
//+------------------------------------------------------------------+
bool IsTP1Managed(int ticket)
{
   return GlobalVariableGet("made_tp1m_" + IntegerToString(ticket)) > 0;
}
void SetTP1Managed(int ticket)
{
   GlobalVariableSet("made_tp1m_" + IntegerToString(ticket), 1);
}
bool IsTP2Managed(int ticket)
{
   return GlobalVariableGet("made_tp2m_" + IntegerToString(ticket)) > 0;
}
void SetTP2Managed(int ticket)
{
   GlobalVariableSet("made_tp2m_" + IntegerToString(ticket), 1);
}

//+------------------------------------------------------------------+
//| Minimal JSON extraction helpers                                  |
//+------------------------------------------------------------------+
string JsonExtractString(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if (start == -1) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if (end == -1) return "";
   return StringSubstr(json, start, end - start);
}

double JsonExtractDouble(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if (start == -1) return 0.0;
   start += StringLen(search);
   while (start < StringLen(json) && StringSubstr(json, start, 1) == " ")
      start++;
   string numStr = "";
   for (int i = start; i < StringLen(json); i++)
   {
      string ch = StringSubstr(json, i, 1);
      if (ch == "," || ch == "}" || ch == "]" || ch == " " || ch == "\n" || ch == "\r")
         break;
      numStr += ch;
   }
   return StringToDouble(numStr);
}

int FindJsonObjectEnd(string json, int startPos)
{
   int depth = 0;
   int len = StringLen(json);
   for (int i = startPos; i < len; i++)
   {
      string ch = StringSubstr(json, i, 1);
      if (ch == "{") depth++;
      else if (ch == "}")
      {
         depth--;
         if (depth == 0) return i;
      }
   }
   return -1;
}
//+------------------------------------------------------------------+
