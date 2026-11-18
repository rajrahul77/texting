4.2 Use Case 2: Denodo MCP Layer and Multi-Agent Workflow System [Author: Rahul Pandey]

Use-Case Description

This use case evaluates how Dataiku agents can use customer data exposed through Denodo MCP, coordinate specialized agents in one user-facing workflow, and finish with human-approved customer emails. Using the Resort360 customer intelligence view (resort360_n.dp_customer_intelligence) in the genai_1 project, the system finds where revenue can grow, picks the customers most likely to respond, assigns each a fixed offer, drafts personalized emails and sends each one only after a person approves it.

The multi-agent split is there to assess Dataiku's orchestration, context passing and tool control; the same logic could run with fewer LLM calls. Simple questions ("Who is the highest-spending customer?") skip the chain and are answered directly, with a chart.

Agents and Responsibilities

All agents run on Gemini 3.8 Flash.

1. Orchestrator - Entry point. Routes each question to one agent, reuses earlier results, drafts and rewrites emails, and is the only component that can send. Data: agent results only.
2. Denodo MCP Agent - Quick answers with charts (top-N, counts, comparisons); fetches names and emails for drafts. Data: live Denodo.
3. Portfolio Opportunity Agent - Where revenue can grow: customers and revenue gap for three levers (conversion, spend, frequency), top 3 states, ideas. Data: live Denodo.
4. Customer Targeting Agent - 10 customers for the chosen lever, ranked by the predictive model's probability; Customer IDs only. Data: live Denodo + scores.
5. Next Best Action Agent - A fixed primary offer per lever, plus a personal angle, channel and timing for the top 5. Data: insights + offers table.
6. send_email (tool) - Sends one email (recipient, subject, message) through the data-platform-mailer SMTP channel after approval.

Offers are deterministic: Conversion -> STD_BKG_EXT (Stay 3 Pay 2), Spend -> REP_DIN_CRED (Resort Dining Credit), Frequency -> REP_ROOM_UP (Complimentary Room Upgrade). The agent copies offers exactly and never invents discounts, prices or dates.

Workflow and Agent Interaction

Each question runs one step, and earlier results in the conversation are reused rather than recomputed:

a.  "Where can we increase sales?" -> Portfolio Opportunity Agent.

b.  "Which customers fit?" -> Customer Targeting Agent, using the lever and states from step a.

c.  "Plan an offer for each" -> Next Best Action Agent.

d.  "Draft the emails" -> Orchestrator gets names and emails once from the Denodo MCP Agent and writes one email per customer.

e.  "Make them more empathetic" -> Orchestrator rewrites the drafts; no agent is called.

f.  "Send" -> Orchestrator sends the latest drafts exactly as written; the user accepts or rejects each email in Agent Hub.

Architecture and Data Flow

-   Access: Agent Hub, embedded in a Dataiku dashboard.

-   Data: live Denodo view, plus Flow datasets for predictive scores, GenAI insights and approved offers.

-   Tools: Denodo MCP, run_vql_for_chart, dataset lookups.

-   Agents and orchestration: the four specialist agents under one Orchestrator.

-   Action: send_email, gated by human approval.

[Figures: recapture the Flow and agent map from genai_1; the current screenshots show the older gpt-4o / General-Purpose-Agent build.]

Charts in Agent Hub

Agent Hub draws a chart only when a tool returns structured records. Denodo MCP returns query results as text, so answers first appeared as plain tables. Dataiku's built-in SQL Query tool returns records, but it supports only PostgreSQL, Snowflake, SQL Server and BigQuery, and the Denodo connection is a Denodo-type JDBC connection.

The fix is a small custom Python agent tool, run_vql_for_chart, attached to the Denodo MCP Agent:

1.  The agent writes and validates one VQL query through Denodo MCP, as before.

2.  For any count, total, average, top-N or breakdown, it calls run_vql_for_chart with the same VQL.

3.  The tool runs the query on the existing Denodo connection and returns the rows three ways: as text for the agent, as a RECORDS artifact that Agent Hub draws as a chart, and as sources (query plus rows) shown under See details.

4.  In Agent Hub, Charts generation is set to Auto (or On demand).

Guardrails: one read-only SELECT only, at most 50 rows, and personal-data columns are dropped. Two issues were fixed on the way: the tool must accept its input as a string as well as JSON, and the records must be returned as an artifact, because records placed only in sources do not produce a chart.

Tools Exposed Through MCP

Denodo MCP gives agents controlled access to the customer data without database logic in each prompt: segment analysis, group comparisons, high-value customers, booking and revenue figures, and selection criteria. Email is not sent through MCP. The growth agents' prompts name the exact view and columns, so agents do not call MCP discovery tools on every run.

Agent-to-Agent Context Sharing

Agents pass short JSON results: Portfolio -> lever, segment and top states; Targeting -> the customer table; Next Best Action -> the offer and plan. The Orchestrator copies these exactly, sends each agent only what it needs, and reuses results already in the conversation. Downstream agents may not change upstream decisions.

Error Handling and Recovery

-   Missing input returns {"status": "no_input"} and the workflow stops instead of guessing.

-   A failed query is fixed once; a second failure stops the workflow.

-   Each agent has a tool-call limit and never re-runs a query to check it.

-   Customers without a score are marked NOT_SCORED, never estimated.

-   Emails are not retried automatically; retry policies are needed before production.

Human Approval Points

Every email shows its recipient, subject and full message in an approval card, one card per email, and nothing is sent without acceptance. This control stays on in all environments. Recommendations need no approval because they trigger no customer-facing action.

Security and Governance

Only agents that need data get data tools; the Orchestrator has only agent tools and send_email. Chat tables show Customer IDs only, and names and emails appear only in drafts and approval cards. Targeting by gender or nationality is refused. Users reach the agents only through Agent Hub inside a dashboard, and the Hub backend runs as a fixed finance-level account instead of "Last modifier", which had changed the visible Denodo views depending on who last edited the webapp. Per-user Denodo roles are not yet applied per person; this is planned as phase 2.

Test Scenarios

Tested with the Agent Hub Activities panel open:

a.  growth opportunity, matching customers and next best action;

b.  highest spender and top customers by revenue, with charts;

c.  each follow-up calls only the agent it needs; rewrite and send call none;

d.  sent emails match the latest drafts exactly;

e.  the same question in a new conversation gives the same lever and figures;

f.  no unsupported offers from Next Best Action; gender targeting is refused.

Results and Observations

Dataiku coordinated multiple agents with clearly separated responsibilities. Explicit context passing and strict prompts reduced generic answers and unsupported statements. Simple questions are better handled by the direct path, and factual values should come from queries, with the LLM interpreting them.

The first version took about 15 minutes per growth question. The LLM was not the bottleneck (about 5 s for a simple reply; 40-50 s per Denodo MCP query). The time came from agents discovering views on every run, retrying queries, rerunning the whole chain on each follow-up, and Gemini 3.1 Pro's long reasoning. Naming the view and columns, limiting tool calls, reusing results and switching to Flash fixed this; final per-step timings should be taken from Trace Explorer.

Scalability and Operational Considerations

This is a PoC for orchestration patterns, not throughput. Each MCP query costs 40-50 s, so the number of queries matters more than the model, and Agent Hub adds its own LLM steps. The shortlist is capped at 10 customers because scores are looked up per customer; large campaigns should run as a batch Flow job. Concurrency, cost, timeouts and logging volume remain to be evaluated.

Risks and Limitations

The predictive model's target equals the repeat-customer flag, so its probability means "similar to our repeat customers", not a likelihood to buy. Some columns are unusable (amenities and longest stay are all zero). Outputs can still vary between runs, the Gemini models are previews, and scores and insights are only as fresh as the last Flow run. Data such as channel preference, offer history or campaign response is unavailable and must not be inferred.

Recommended Improvements

Already in place: JSON contracts between agents, fixed offers, human approval and trace monitoring. Next:

-   validate customer IDs and key metrics against the dataset before they reach the answer;

-   per-user identity so each user's Denodo role applies;

-   automated evaluation of common conversations, with latency and token tracking;

-   one tool call for all scores, so the shortlist can grow beyond 10;

-   consent data before emails go to real customers.
