4.2 Use Case 2: Denodo MCP Layer and Multi-Agent Workflow System [Author: Rahul Pandey]


USE-CASE DESCRIPTION

This use case evaluates how Dataiku agents can use enterprise customer data exposed through Denodo MCP, coordinate several specialized agents in one user-facing workflow, and complete that workflow with human-approved customer emails. The implementation uses the Resort360 customer intelligence view (resort360_n.dp_customer_intelligence) in the genai_1 project.

The system answers a sequence of business questions: where revenue can grow, which customers are most likely to respond, what offer and approach suits each customer, and what email to send them. Each email is sent only after a person approves it.

The solution is split into specialized agents to evaluate orchestration, context passing, tool usage and control between agents. The same business logic could be implemented with fewer LLM calls; the multi-agent design is there to assess Dataiku's orchestration capabilities, not because the use case requires it.

A quick-answer path is also available, so users are not limited to the growth workflow. Questions such as "Who is the highest-spending customer?" or "Show the customer count by value segment" are answered directly from the customer data, with a chart, without running the full chain.


AGENTS AND RESPONSIBILITIES

All agents run on Gemini 3.8 Flash. Earlier versions used Gemini 3.1 Pro and gpt-4o; Flash was chosen for speed once the prompts were made precise.

1. Orchestrator (Customer_Intelligence_Orchestrator)
The Orchestrator is the user-facing entry point. It classifies each request and calls only the agent that step needs. Before calling any agent, it reuses results already shown in the conversation (the opportunity, the customer list, the plan and the email drafts), so a follow-up question does not rerun earlier steps. It does not query customer data itself.
It writes the email drafts and rewrites them on request, for example in a warmer or more empathetic tone, without calling another agent. It is the only component allowed to use the email tool, and it sends the latest drafts exactly as written, one email per recipient.

2. Denodo MCP Agent (quick answers)
This agent replaces the earlier General-Purpose Customer Intelligence Agent. It answers factual and analytical questions that do not need the full workflow, such as:
- highest or lowest spending customer;
- top-N customers by revenue;
- booking counts and average customer metrics;
- customer-level lookups;
- segment comparisons, filtering and ranking.
It keeps a conversation on one Data Product (view), writes one VQL query, and returns the result as a chart (see Charts in Agent Hub). The Orchestrator also calls it once to fetch customer names and email addresses when drafting emails.

3. Portfolio Opportunity Agent
This agent analyses the whole customer base across three growth levers, each benchmarked against the average repeat customer:
- Conversion: one-time customers who could become repeat customers.
- Spend: repeat customers who spend less per booking than the benchmark.
- Frequency: repeat customers who spend well per booking but book less often than the benchmark.
In at most two live queries it returns the number of customers and the revenue gap for each lever, the recommended lever, its priority, the top 3 states and one practical idea per lever. It does not select individual customers or define the action.

4. Customer Targeting Agent
This agent receives the lever, segment and top states as a fixed input. One live query returns 10 candidate customers with their bookings, lifetime revenue, revenue per booking, average stay and revenue gap. It then ranks them by the probability from the predictive model's scores dataset (from the last Flow run). Customers without a score are listed last as NOT_SCORED; scores are never guessed.
It returns Customer Identifiers only. Names and email addresses are not passed between agents; they are fetched only when the emails are drafted.

5. Next Best Action Agent
This agent receives the lever and the customer list and turns them into a plan per customer. The offer is deterministic: each lever maps to one primary offer from the approved resort offers table.
- Conversion -> STD_BKG_EXT (Stay 3 Pay 2)
- Spend -> REP_DIN_CRED (Resort Dining Credit)
- Frequency -> REP_ROOM_UP (Complimentary Room Upgrade)
It may add one supporting offer for a customer only when that customer's GenAI insight clearly supports it. The top 5 customers by score get a personal angle, channel and timing; the rest receive the primary offer as a campaign. The agent copies offer IDs, names and details exactly, and must not invent discounts, prices, dates, conversion rates or campaign targets.

6. Email Action (send_email tool)
Customer emails are sent through a Dataiku Send Message tool, send_email, using the data-platform-mailer (smtp) channel. The tool takes three parameters: recipient, subject and message. It is an action, not an agent: it performs no reasoning, and every call passes through a human approval step before it runs.


WORKFLOW AND AGENT INTERACTION

The Orchestrator first checks what the conversation already holds, then classifies the request. A direct analytical question goes to the Denodo MCP Agent and skips the chain. A customer-growth conversation runs one step per question:

a. "Where can we increase sales?" - the Portfolio Opportunity Agent returns the three levers, the recommended lever and the top states.
b. "Which customers fit this?" - the Orchestrator reuses the lever and states from step a and passes them to the Customer Targeting Agent, which returns 10 ranked customers.
c. "Plan an offer for each customer" - the Next Best Action Agent receives the lever and the customer table and returns the primary offer and a plan per customer.
d. "Draft the emails" - the Orchestrator gets the names and email addresses of those customers once from the Denodo MCP Agent, then writes one email per customer from the plan and its offer.
e. "Make them more empathetic" (optional) - the Orchestrator rewrites the drafts itself; no agent is called.
f. "Send these emails" - the Orchestrator calls send_email once per draft, using the latest drafts exactly as written.
g. Agent Hub shows the recipient, subject and message of each email, and the user accepts or rejects it. Accepted emails go out through SMTP; rejected ones are not sent, and nothing is retried automatically.

If the request asks only for a recommendation, the workflow ends at step c and no email is drafted. If the user names a different lever, the Portfolio Opportunity Agent runs again for that lever. A request for the full plan in one go runs steps a to c in sequence.


ARCHITECTURE AND DATA FLOW

The architecture has six layers:
- Access layer: Agent Hub, embedded in a Dataiku dashboard, as the only user-facing entry point.
- Data layer: live customer data in Denodo, plus Flow datasets from the last run: predictive scores, GenAI customer insights and the approved resort offers.
- Tool layer: Denodo MCP for live queries, run_vql_for_chart for chartable results, and dataset lookups for scores, insights and offers.
- Agent layer: specialized agents for portfolio analysis, targeting, next best action and direct analytics.
- Orchestration layer: the Orchestrator, which routes each step, reuses context and prepares the emails.
- Action layer: send_email, gated by human approval, sending through the data-platform-mailer (smtp) channel.

[Figures: recapture the Flow and the agent map from genai_1. The current screenshots come from the earlier build and still show gpt-4o and the General-Purpose-Agent.]


CHARTS IN AGENT HUB

Agent Hub can draw a chart only when a tool returns its result as structured records. Denodo MCP returns query results as text, so in the first version answers appeared only as plain tables. Dataiku's built-in SQL Query tool does return records, but it supports only PostgreSQL, Snowflake, SQL Server and BigQuery connections, and the Denodo connection is a Denodo-type JDBC connection, so it could not be used.

The solution is a small custom Python agent tool, run_vql_for_chart, attached to the Denodo MCP Agent. It works in four steps:
1. The agent writes and validates one VQL query through Denodo MCP, exactly as before.
2. For any count, total, average, top-N or breakdown, the agent calls run_vql_for_chart with the same VQL. The agent's prompt makes this a rule and tells it not to run the query twice or draw charts in text.
3. The tool runs the query on the existing Denodo connection and returns the result three ways: as text for the agent to summarize, as a RECORDS artifact that Agent Hub draws as a chart, and as sources (the query and the rows) that users can open under See details.
4. In the Agent Hub settings, Charts generation is set to Auto, so a chart appears with each answer (On demand is an option if speed matters more).

The tool has built-in guardrails: it accepts only a single read-only SELECT, returns at most 50 rows, and drops personal-data columns (names, emails, phone numbers, addresses) before anything reaches the chat.

Two issues were fixed during development. The tool first failed because the agent sometimes sent its input as a plain string instead of JSON, so the tool now accepts both. Charts then still did not appear because the records were returned only as sources; Agent Hub draws charts only from an artifact, so the records are now returned as an artifact as well.


TOOLS EXPOSED THROUGH MCP

Denodo MCP is used to provide agents with controlled access to the Resort360 customer intelligence data. The MCP layer allows agents to inspect available data and execute analytical requests without embedding database-specific access logic in each agent's prompt.

Typical use cases include:
a. analyzing customer segments;
b. comparing customer groups;
c. identifying high-value customers;
d. retrieving booking and revenue information;
e. supporting customer selection criteria.

Email sending is not exposed through MCP; it is handled by the separate send_email tool.

For deterministic questions such as maximum, minimum, top N, counts, averages and rankings, the result must come from structured data rather than be inferred by the LLM, which is why the query result is returned as records through run_vql_for_chart. The growth agents' prompts also name the exact view and columns, so agents do not call MCP discovery tools (list, search, describe) on every run. That discovery was the main cause of slowness in the first version.


AGENT-TO-AGENT CONTEXT SHARING

Agent outputs are passed explicitly between stages as short JSON results, rather than assuming downstream agents know previous decisions. The Customer Targeting Agent receives the lever, segment and top states from the Portfolio Opportunity Agent; the Next Best Action Agent receives the lever and the customer table. The Orchestrator copies these values exactly and sends each agent only what it needs, not the whole conversation.

Results already shown in the conversation are reused on follow-up questions instead of being regenerated. This keeps answers consistent from step to step, makes it easier to trace how a recommendation was produced, and avoids repeated agent calls. Downstream agents are instructed not to change upstream decisions such as the lever, the selected customers or the offer.


ERROR HANDLING AND RECOVERY

The Orchestrator acts as a control point between agents. If an agent returns an incomplete or contradictory response, the result is not passed to the next stage. The current control rules are:
a. an agent returns {"status": "no_input"} when a required input is missing, and the workflow stops instead of guessing;
b. a failed query is corrected once; if it fails again, the workflow stops;
c. each agent has a fixed limit on tool calls and never re-runs a query to check it;
d. customers without a score are marked NOT_SCORED instead of being given an estimate;
e. structured customer data is treated as the source of truth when it conflicts with generated text;
f. if the drafts have no recipient address, the send step stops and asks the user to draft the emails first;
g. emails are not retried automatically. Further retry policies and recovery mechanisms would need to be formalized before production.


HUMAN APPROVAL POINTS

Human approval is enforced before any email is sent. For each email, Agent Hub shows the recipient, subject and full message in an approval card, and the user must accept or reject it. Nothing is sent without acceptance, and sending ten emails means ten separate decisions. The Orchestrator does not ask for confirmation in text; the approval card is the confirmation.

This control stays enabled in all environments. Removing it or sending automatically would require an explicit change in requirements and a separate review. For demonstrations, the recipient can be pointed at a test inbox. Recommendations themselves do not need approval, because they trigger no customer-facing action.


SECURITY AND GOVERNANCE

The solution separates data access from orchestration. Only agents that need customer data are given MCP or dataset tools; the Orchestrator holds only the agent tools and send_email. Dataset lookups are limited to the Customer Identifier plus the score, insight or offer columns.

Customer-level structured fields are the source of truth, and LLM-generated insights are used only as supporting context. Tables in the chat show Customer Identifiers only; names and email addresses appear only inside email drafts and approval cards. Requests to target or rank customers by gender or nationality are refused.

Agent Hub is the user-facing access layer, so the specialist agents are not exposed individually to business users. The Hub is embedded in a dashboard: users receive Read dashboards permission, and the Hub and published agents are added as authorized objects. The Hub backend runs under a fixed finance-level account rather than "Last modifier"; with "Last modifier", the Denodo views visible to everyone changed depending on who had last edited the webapp.

Per-user Denodo roles (for example, a resort administrator seeing four views and a financial administrator seeing two) are not yet enforced per person, because the Denodo connection uses a shared service user and the tools run under the backend identity. Per-user access is planned as a second phase.


TEST SCENARIOS

The workflow was tested with both end-to-end business conversations and direct analytical questions, using the Agent Hub Activities panel to check which agents and tools each step called. Representative scenarios include:
a. identify a customer-growth opportunity and recommend the next best action;
b. identify actual customers matching an opportunity;
c. determine the highest-spending customer and the top customers by lifetime revenue, with charts;
d. compare repeat and standard customers;
e. check that each follow-up question calls only the agent it needs, and that rewriting and sending call none;
f. check that the sent emails match the latest drafts exactly;
g. ask the same growth question in a new conversation and check that the lever and figures are the same;
h. test whether the Next Best Action Agent introduces unsupported offers or customer assumptions;
i. request gender-based targeting and check that it is refused.


RESULTS AND OBSERVATIONS

The PoC demonstrated that Dataiku can coordinate multiple agents while keeping individual responsibilities separated. Explicit context passing between agents was important: when upstream information was not clearly passed downstream, responses became generic or introduced assumptions. Stricter prompts also reduced unsupported statements, particularly in the Next Best Action stage.

Not every question benefits from the multi-agent workflow. Rankings, counts and direct customer lookups are better handled through the direct analytical path. Factual customer values should come from structured queries; LLM reasoning is more useful for interpreting those values and forming recommendations.

Performance was the main challenge. The first version took about 15 minutes for one growth question, with the Portfolio Opportunity Agent alone taking more than 10 minutes. The LLM itself was not the bottleneck: the Orchestrator answered a simple message in about 5 seconds, and one Denodo MCP query took 40-50 seconds. The time went into agents discovering views and columns on every run, retrying queries, rerunning the whole chain on every follow-up, and the long reasoning passes of Gemini 3.1 Pro. Naming the exact view and columns in the prompts, limiting tool calls, reusing earlier results and switching to Gemini Flash removed most of this delay. Final per-step timings should be recorded from Trace Explorer.

Two further lessons came from the email step. The send step originally called other agents again and replaced the user's rewritten drafts with a new generic email; an explicit rule to send the latest drafts exactly fixed this. And when two agents were selected in the same Agent Hub chat, the Hub's own LLM sometimes routed "send" to the wrong agent, so each conversation now uses one agent.


SCALABILITY AND OPERATIONAL CONSIDERATIONS

The current implementation is a PoC designed to validate orchestration patterns rather than production-scale throughput. A multi-agent request results in several LLM and tool calls, which adds latency and token usage compared with a single-agent implementation, so the Orchestrator invokes only the agents a request needs.

Each Denodo MCP query takes 40-50 seconds, so the number of queries per step matters more than the model, and Agent Hub adds its own LLM steps before and after each agent. The customer shortlist is capped at 10 because scores are looked up per customer; large campaigns should run as a batch Flow job rather than in chat. At larger scale, request concurrency, MCP query performance, LLM cost, timeout handling and logging volume still need to be evaluated.


RISKS AND LIMITATIONS

Customers are ranked by the predictive model's probability. However, the model's target (customer value segment) is identical to the repeat-customer flag, so the probability means "similar to our repeat customers", not a measured likelihood to buy, and the system presents it that way. Some columns are also unusable: the amenity and longest-stay columns are all zero.

Agent outputs may still vary between runs because the orchestration relies on LLM reasoning, and the Gemini models used are previews, so tests must be re-run when a version changes. Scores, insights and offers are only as fresh as the last Flow run, while customer facts are live.

The quality of the recommendation is limited by the attributes in the customer intelligence dataset. Where channel preference, offer history, campaign response or recency data is unavailable, the system should not infer those values. The value of the current design is in demonstrating controlled delegation, tool usage, context passing and governance, not in claiming that multi-agent execution is inherently superior.


RECOMMENDED IMPROVEMENTS

Several earlier recommendations are now in place: JSON output contracts between agents, deterministic offers from an approved offers table, human approval before any customer-facing action, and trace monitoring through Trace Explorer.

The next improvement should be deterministic verification of customer-level values: Customer IDs and key metrics returned by an agent can be validated against the structured customer dataset before being included in the final response.

Additional improvements include:
- per-user identity, so each user's Denodo role applies to their own questions;
- automated evaluation scenarios for common user conversations;
- capturing latency and token consumption per workflow from the traces;
- fetching all scores in one tool call, so the shortlist can grow beyond 10 customers;
- consent data before emails go to real customers instead of a test inbox.
