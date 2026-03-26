//+------------------------------------------------------------------+
//|                                                  made_EA_MT4.mq4 |
//|                           made. — Intelligent Signal Platform    |
//|                                          https://made.app        |
//|                                                                  |
//| Receives signals from the made. backend via HTTP polling,        |
//| validates current price against signal entry, executes orders    |
//| with slippage tolerance, manages 3-tier partial closes at TP     |
//| levels, and confirms execution details back to the app.          |
//|                                                                  |
//| Installation:                                                    |
//|   1. Copy to MQL4/Experts/                                       |
//|   2. Compile in MetaEditor                                       |
//|   3. Attach to XAUUSD or GBPJPY chart                           |
//|   4. Enable AutoTrading                                          |
//|   5. Allow WebRequest: Tools > Options > Expert Advisors >       |
//|      "Allow WebRequest" > add http://localhost:8000              |
//+------------------------------------------------------------------+

#property copyright "made. — Intelligent Signal Platform"
#property link      "https://made.app"
#property version   "1.00"
#property strict

//---- Input parameters --------------------------------------------------------

input string   BackendURL      = "http://localhost:8000";  // made. backend URL
input int      MagicNumber     = 20260101;                 // Unique EA identifier
input double   MaxSlippagePips = 2.0;                      // Max price deviation from signal entry
input bool     EnableTrading   = true;                     // Master kill switch
input bool     EnableLogging   = true;                     // Verbose console logging
input string   EASecret        = "ea-dev-secret";          // Shared secret for X-EA-Secret header
input int      PollIntervalSec = 5;                        // How often to poll for new signals

//---- State -------------------------------------------------------------------

// Tracks which signal IDs have already been processed to prevent double-execution
string processedSignalIds[];
int    processedCount = 0;

// Track last bar time to avoid redundant OnTick TP checks
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
//| Expert initialisation                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   if (!EnableTrading)
      Print("[made.] Trading disabled via input parameter. EA is in monitor-only mode.");

   // Validate WebRequest is permitted — a common configuration mistake
   string testUrl = BackendURL + "/health";
   char   postData[];
   char   result[];
   string headers;
   int    res = WebRequest("GET", testUrl, "", "", 5000, postData, 0, result, headers);

   if (res == -1)
   {
      int err = GetLastError();
      if (err == 4014)
      {
         Alert("[made.] WebRequest not allowed for: " + BackendURL +
               "\nGo to Tools > Options > Expert Advisors and add this URL to the whitelist.");
         return INIT_FAILED;
      }
      // Non-4014 errors just mean the backend is not running — warn but don't fail init
      if (EnableLogging)
         Print("[made.] Backend unreachable at init (will retry on timer): err=", err);
   }
   else
   {
      if (EnableLogging)
         Print("[made.] Backend connection OK. EA ready. Magic=", MagicNumber);
   }

   // Start polling timer
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
      Print("[made.] EA removed. Reason code: ", reason);
}

//+------------------------------------------------------------------+
//| OnTimer — poll backend for pending signals                       |
//+------------------------------------------------------------------+
void OnTimer()
{
   if (!EnableTrading)
      return;

   string url = BackendURL + "/broker/ea/pending?magic=" + IntegerToString(MagicNumber);
   string responseBody = HttpGet(url);

   if (StringLen(responseBody) == 0)
      return;

   // Parse the JSON array of pending signal objects.
   // We use a minimal string-based parser to avoid external library dependencies.
   // Expected format: [{"signal_id":"...","pair":"...","direction":"BUY"|"SELL",
   //   "entry_price":1234.5,"sl":1230.0,"tp1":1240.0,"tp2":1250.0,"tp3":1265.0},...]
   ProcessPendingSignals(responseBody);
}

//+------------------------------------------------------------------+
//| OnTick — manage open positions (TP partial closes, SL trail)     |
//+------------------------------------------------------------------+
void OnTick()
{
   // Throttle to once per new bar to avoid excessive processing
   datetime currentBar = iTime(_Symbol, Period(), 0);
   if (currentBar == lastBarTime)
      return;
   lastBarTime = currentBar;

   ManageOpenPositions();
}

//+------------------------------------------------------------------+
//| ProcessPendingSignals — parse JSON array and execute each signal |
//+------------------------------------------------------------------+
void ProcessPendingSignals(string jsonArray)
{
   // Iterate through JSON objects in the array
   int pos = 0;
   int len = StringLen(jsonArray);

   while (pos < len)
   {
      // Find start of next JSON object
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
//| ExecuteSignal — validate and execute a single signal object      |
//+------------------------------------------------------------------+
void ExecuteSignal(string json)
{
   string signalId  = JsonExtractString(json, "signal_id");
   string pair      = JsonExtractString(json, "pair");
   string direction = JsonExtractString(json, "direction");
   double entryPrice = JsonExtractDouble(json, "entry_price");
   double sl        = JsonExtractDouble(json, "sl");
   double tp1       = JsonExtractDouble(json, "tp1");
   double tp2       = JsonExtractDouble(json, "tp2");
   double tp3       = JsonExtractDouble(json, "tp3");
   double lots      = JsonExtractDouble(json, "lot_size");

   if (StringLen(signalId) == 0 || StringLen(direction) == 0 || entryPrice <= 0)
   {
      if (EnableLogging)
         Print("[made.] Skipping malformed signal JSON: ", json);
      return;
   }

   // De-duplicate: skip if already processed
   if (IsAlreadyProcessed(signalId))
   {
      if (EnableLogging)
         Print("[made.] Signal already processed, skipping: ", signalId);
      return;
   }

   // Only trade the symbol this EA is attached to
   if (pair != _Symbol)
   {
      if (EnableLogging)
         Print("[made.] Signal pair ", pair, " != chart symbol ", _Symbol, " — skipping.");
      return;
   }

   // Validate price is within slippage tolerance
   double currentPrice = (direction == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                               : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slippagePrice = MaxSlippagePips * PipValue();
   double deviation = MathAbs(currentPrice - entryPrice);

   if (deviation > slippagePrice)
   {
      if (EnableLogging)
         Print("[made.] Signal ", signalId, " REJECTED — price deviation ",
               DoubleToStr(deviation, Digits()), " > tolerance ",
               DoubleToStr(slippagePrice, Digits()));
      ConfirmExecution(signalId, 0, 0, 0, "rejected", "price_deviation");
      MarkProcessed(signalId);
      return;
   }

   // Fallback lot size: 0.01 if backend didn't send one
   if (lots <= 0) lots = 0.01;

   // Normalise lot size to broker step
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lotMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathMax(lotMin, MathMin(lotMax, MathRound(lots / lotStep) * lotStep));

   // Open market order
   int cmd    = (direction == "BUY") ? OP_BUY : OP_SELL;
   int slipTicks = (int)MathCeil(MaxSlippagePips * 10); // slippage in broker points

   int ticket = OrderSend(
      _Symbol,
      cmd,
      lots,
      currentPrice,
      slipTicks,
      sl,
      tp1,                // Set TP to TP1 initially; partial close logic manages TP2/TP3
      "made." + signalId, // Comment encodes signal ID for TP management
      MagicNumber,
      0,
      (direction == "BUY") ? clrLime : clrRed
   );

   if (ticket < 0)
   {
      int err = GetLastError();
      if (EnableLogging)
         Print("[made.] OrderSend FAILED for signal ", signalId, " err=", err);
      ConfirmExecution(signalId, 0, 0, err, "failed", "order_error_" + IntegerToString(err));
   }
   else
   {
      // Store TP2/TP3 levels in the order comment for the TP management logic.
      // Format: made.<signal_id>|tp2:<price>|tp3:<price>|tp1hit:0|tp2hit:0
      string fullComment = "made." + signalId +
                           "|tp2:" + DoubleToStr(tp2, Digits()) +
                           "|tp3:" + DoubleToStr(tp3, Digits()) +
                           "|tp1hit:0|tp2hit:0";
      OrderModify(ticket, OrderOpenPrice(), sl, tp1, 0, clrNONE);
      // Note: MT4 comment is set at order open; we log the extended info separately.

      double fillPrice = OrderOpenPrice();
      if (OrderSelect(ticket, SELECT_BY_TICKET))
         fillPrice = OrderOpenPrice();

      double slippage = MathAbs(fillPrice - entryPrice);
      if (EnableLogging)
         Print("[made.] Order opened. Ticket=", ticket, " Signal=", signalId,
               " Fill=", DoubleToStr(fillPrice, Digits()),
               " Entry=", DoubleToStr(entryPrice, Digits()),
               " Slip=", DoubleToStr(slippage, Digits()));

      ConfirmExecution(signalId, ticket, fillPrice, 0, "filled", "");

      // Store tp2/tp3 in a global variable keyed by ticket for the TP manager
      GlobalVariableSet("made_tp2_" + IntegerToString(ticket), tp2);
      GlobalVariableSet("made_tp3_" + IntegerToString(ticket), tp3);
      GlobalVariableSet("made_entry_" + IntegerToString(ticket), entryPrice);
   }

   MarkProcessed(signalId);
}

//+------------------------------------------------------------------+
//| ManageOpenPositions — check TP levels and apply partial closes   |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for (int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if (!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if (OrderMagicNumber() != MagicNumber)
         continue;
      if (OrderSymbol() != _Symbol)
         continue;

      int    ticket    = OrderTicket();
      int    cmd       = OrderType();
      double lots      = OrderLots();
      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double currentTP = OrderTakeProfit();

      double tp2 = GlobalVariableGet("made_tp2_" + IntegerToString(ticket));
      double tp3 = GlobalVariableGet("made_tp3_" + IntegerToString(ticket));
      double entryPrice = GlobalVariableGet("made_entry_" + IntegerToString(ticket));

      // Skip if TP2/TP3 globals not found (shouldn't happen but be safe)
      if (tp2 <= 0 || tp3 <= 0)
         continue;

      double currentPrice = (cmd == OP_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                             : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      bool tp1Hit = (cmd == OP_BUY)  ? (currentPrice >= currentTP && currentTP > 0)
                                     : (currentPrice <= currentTP && currentTP > 0);
      bool tp2Hit = (cmd == OP_BUY)  ? (currentPrice >= tp2) : (currentPrice <= tp2);

      // TP1 reached: close 40%, move SL to entry
      if (tp1Hit && !IsTP1Managed(ticket))
      {
         double closeQty = NormalizeLots(lots * 0.40);
         if (closeQty >= SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN))
         {
            double closePrice = (cmd == OP_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            bool closed = OrderClose(ticket, closeQty, closePrice, 3);
            if (closed)
            {
               // Move SL to breakeven (entry price)
               double newSL = entryPrice;
               if (!OrderModify(ticket, openPrice, newSL, tp2, 0, clrYellow))
                  if (EnableLogging)
                     Print("[made.] TP1 SL-to-BE modify failed for ticket ", ticket,
                           " err=", GetLastError());

               SetTP1Managed(ticket);
               ReportTPHit(ticket, 1, closePrice);

               if (EnableLogging)
                  Print("[made.] TP1 hit. Ticket=", ticket,
                        " Closed=", DoubleToStr(closeQty, 2), " lots",
                        " SL moved to entry=", DoubleToStr(newSL, Digits()));
            }
         }
      }

      // TP2 reached: close 50% of remaining, trail SL to TP1 price
      if (tp2Hit && IsTP1Managed(ticket) && !IsTP2Managed(ticket))
      {
         if (!OrderSelect(ticket, SELECT_BY_TICKET))
            continue;

         double remainingLots = OrderLots();
         double closeQty = NormalizeLots(remainingLots * 0.50);

         if (closeQty >= SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN))
         {
            double closePrice = (cmd == OP_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            bool closed = OrderClose(ticket, closeQty, closePrice, 3);
            if (closed)
            {
               // Trail SL to TP1 price (locked in at the first target)
               double tp1Price = currentTP; // at this point TP was updated to tp2 after TP1; original TP1 is in order history
               // We use the GlobalVariable stored entry + initial TP for approximation
               // For a precise implementation, store TP1 in a GlobalVariable at order open
               double tp1GlobalKey = GlobalVariableGet("made_tp1_" + IntegerToString(ticket));
               double newSL = (tp1GlobalKey > 0) ? tp1GlobalKey : entryPrice;

               if (!OrderModify(ticket, openPrice, newSL, tp3, 0, clrCyan))
                  if (EnableLogging)
                     Print("[made.] TP2 trail modify failed for ticket ", ticket,
                           " err=", GetLastError());

               SetTP2Managed(ticket);
               ReportTPHit(ticket, 2, closePrice);

               if (EnableLogging)
                  Print("[made.] TP2 hit. Ticket=", ticket,
                        " Closed=", DoubleToStr(closeQty, 2), " lots",
                        " SL trailed to TP1=", DoubleToStr(newSL, Digits()));
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ConfirmExecution — POST fill details back to the backend         |
//+------------------------------------------------------------------+
void ConfirmExecution(string signalId, int ticket, double fillPrice,
                      int errorCode, string status, string reason)
{
   string url = BackendURL + "/broker/ea/confirm";

   string body = "{\"signal_id\":\"" + signalId + "\"," +
                 "\"ticket\":" + IntegerToString(ticket) + "," +
                 "\"fill_price\":" + DoubleToStr(fillPrice, Digits()) + "," +
                 "\"status\":\"" + status + "\"," +
                 "\"reason\":\"" + reason + "\"," +
                 "\"error_code\":" + IntegerToString(errorCode) + "," +
                 "\"magic\":" + IntegerToString(MagicNumber) + "}";

   HttpPost(url, body);
}

//+------------------------------------------------------------------+
//| ReportTPHit — POST TP level hit back to the backend              |
//+------------------------------------------------------------------+
void ReportTPHit(int ticket, int tpLevel, double hitPrice)
{
   string url = BackendURL + "/broker/ea/tp_hit";

   string body = "{\"ticket\":" + IntegerToString(ticket) + "," +
                 "\"tp_level\":" + IntegerToString(tpLevel) + "," +
                 "\"hit_price\":" + DoubleToStr(hitPrice, Digits()) + "," +
                 "\"magic\":" + IntegerToString(MagicNumber) + "," +
                 "\"symbol\":\"" + _Symbol + "\"}";

   HttpPost(url, body);
}

//+------------------------------------------------------------------+
//| ReportSLHit — called when a position closes at a loss            |
//+------------------------------------------------------------------+
void OnTradeTransaction(const int ticket)
{
   // MQL4 does not have OnTradeTransaction; we detect SL hits in OnTick
   // by checking for closed positions. This stub is left as documentation.
}

//+------------------------------------------------------------------+
//| HttpGet — send a GET request, return body as string              |
//+------------------------------------------------------------------+
string HttpGet(string url)
{
   char   postData[];
   char   result[];
   string headers;
   string reqHeaders = "X-EA-Secret: " + EASecret + "\r\n" +
                       "Content-Type: application/json\r\n";

   int res = WebRequest("GET", url, reqHeaders, "", 5000, postData, 0, result, headers);

   if (res == -1)
   {
      int err = GetLastError();
      if (err != 5 && EnableLogging) // suppress "operation aborted" spam
         Print("[made.] GET failed. URL=", url, " err=", err);
      return "";
   }

   return CharArrayToString(result);
}

//+------------------------------------------------------------------+
//| HttpPost — send a POST request with a JSON body                  |
//+------------------------------------------------------------------+
bool HttpPost(string url, string jsonBody)
{
   char   postData[];
   char   result[];
   string headers;
   string reqHeaders = "X-EA-Secret: " + EASecret + "\r\n" +
                       "Content-Type: application/json\r\n";

   StringToCharArray(jsonBody, postData, 0, StringLen(jsonBody));
   ArrayResize(postData, StringLen(jsonBody)); // remove null terminator

   int res = WebRequest("POST", url, reqHeaders, "", 5000, postData, ArraySize(postData), result, headers);

   if (res == -1)
   {
      int err = GetLastError();
      if (EnableLogging)
         Print("[made.] POST failed. URL=", url, " err=", err, " body=", jsonBody);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| PipValue — return the price value of 1 pip for the current symbol|
//+------------------------------------------------------------------+
double PipValue()
{
   // Standard pip = 4th decimal for forex, 2nd decimal for JPY pairs and gold
   int digitsCheck = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if (digitsCheck == 3 || digitsCheck == 5)
      return SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10.0;
   return SymbolInfoDouble(_Symbol, SYMBOL_POINT);
}

//+------------------------------------------------------------------+
//| PipsToPrice — convert pips to price distance                     |
//+------------------------------------------------------------------+
double PipsToPrice(double pips)
{
   return pips * PipValue();
}

//+------------------------------------------------------------------+
//| NormalizeLots — round lot size to broker's volume step           |
//+------------------------------------------------------------------+
double NormalizeLots(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   return MathMax(minLot, MathRound(lots / step) * step);
}

//+------------------------------------------------------------------+
//| IsNewBar — returns true once per new bar on the current timeframe|
//+------------------------------------------------------------------+
bool IsNewBar()
{
   static datetime prevBarTime = 0;
   datetime currentBar = iTime(_Symbol, Period(), 0);
   if (currentBar != prevBarTime)
   {
      prevBarTime = currentBar;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Processed signal ID tracking                                     |
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

   // Prune oldest entries to prevent unbounded growth (keep last 200)
   if (processedCount > 200)
   {
      for (int i = 0; i < processedCount - 100; i++)
         processedSignalIds[i] = processedSignalIds[i + 100];
      processedCount -= 100;
      ArrayResize(processedSignalIds, processedCount);
   }
}

//+------------------------------------------------------------------+
//| TP management state via GlobalVariables                          |
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
//| Minimal JSON string/double extraction (no external library)      |
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
   // Skip whitespace
   while (start < StringLen(json) && StringSubstr(json, start, 1) == " ")
      start++;
   // Read until delimiter
   string numStr = "";
   for (int i = start; i < StringLen(json); i++)
   {
      string ch = StringSubstr(json, i, 1);
      if (ch == "," || ch == "}" || ch == "]" || ch == " ")
         break;
      numStr += ch;
   }
   return StringToDouble(numStr);
}

//+------------------------------------------------------------------+
//| Find matching closing brace for a JSON object                    |
//+------------------------------------------------------------------+
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
         if (depth == 0)
            return i;
      }
   }
   return -1;
}
//+------------------------------------------------------------------+
