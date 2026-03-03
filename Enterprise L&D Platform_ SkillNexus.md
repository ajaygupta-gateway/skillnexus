# **AI-Powered Roadmap Platform: SkillNexus**

Role: Senior Full-Stack Engineer / System Architect

Project Duration: 6 hours

Objective: Design and build "SkillNexus," an interactive Roadmap-based Learning Platform (similar to roadmap.sh). The system replaces passive video watching with active, node-based learning paths supported by an AI Tutor.

## **📝 Assignment Deliverables**

1. **Functional MVP:** A working application focusing on the interactive Roadmap UI and AI Chat.  
2. **Source Code:** GitHub/GitLab.

---

# **1\. Executive Summary**

**SkillNexus** transforms L\&D from a repository of videos into dynamic "Learning Journeys." Employees are assigned interactive roadmaps (e.g., "React Developer 2026"). They progress by unlocking nodes, validating knowledge via an AI Tutor, and earning XP/Points for the leaderboard. The L\&D department tracks skill acquisition at a granular node level.

# **2\. Problem Statement**

Traditional LMS platforms are passive (watching videos). Employees need structure—a step-by-step visual map of what to learn next. They also lack instant mentorship. SkillNexus solves this by visualizing the learning path and providing an always-on AI Tutor to explain concepts within that path.


# **3\. Functional Modules & Requirements**

### **3.1 Module A: User Profile & Gamification (The "Player")**

**Goal:** Manage identity and motivate the learner.

* **Auth:** Secure Login/Signup (Role: Learner, Admin).  
* **Profile:** Display Name, Current Role, "XP" (Experience Points), Level (e.g., "Level 5 Developer").  
* **The "Wallet" (Points):** Every action (Login, Node Completion, Streak) awards points.

| Feature | Requirement Detail |
| :---- | :---- |
| **Gamification** | Database must track UserPoints. Logic: Complete Node \= 50 XP. 7-day Streak \= 100 XP bonus. |
| **Leaderboard** | Display "Top Learners this Week" based on XP earned. |
| **Resume Parsing** | (Retained from previous scope) Upload Resume \-\> Extract Skills \-\> Auto-suggest a Roadmap (e.g., "We see you know JS, here is the Advanced React Roadmap"). |



### **3.2 Module B: The Interactive Roadmap Engine (Core UI/UX)**

**Goal:** Replicate the visual, node-based experience of roadmap.sh.

* **Roadmap Rendering:** Display a visual path (Directed Acyclic Graph or Tree).  
  * *Example:* "Frontend" (Root) \-\> "HTML" (Child) \-\> "CSS" (Child).  
* **Node Interaction:** Clicking a node (e.g., "React Hooks") opens a sidebar/modal with:  
  * Description of the topic.  
  * Links to external resources (Docs, Articles).  
  * Status Toggle: "Pending", "In Progress", "Done".  
* **State Management:** Visual indicators for status (Grey \= Locked, Yellow \= In Progress, Green \= Done).

| Feature | Requirement Detail |
| :---- | :---- |
| **Data Structure** | Design a schema to store hierarchical or graph data (Nodes, Edges/Children). |
| **Admin Builder** | A simple interface for L\&D Admins to create a roadmap (JSON editor is acceptable for MVP, Drag-and-drop is Bonus). |
| **Progress** | Track user progress per node. "User X has completed node ID 45 in Roadmap Y". |


  


 

### **3.3 Module C: The AI Tutor Chatbot (Context-Aware)**

**Goal:** Eliminate the need for a human mentor for basic queries.

* **Contextual Chat:** When a user is viewing the "React Hooks" node, the Chatbot automatically knows the context is "React Hooks."  
* **Q\&A:** User asks "Explain useEffect simply," and the AI answers.  
* **Verification:** User can say "Quiz me on this topic." The AI generates a quick question. If the user answers correctly, the AI suggests marking the node as "Done."

| Feature | Requirement Detail |
| :---- | :---- |
| **LLM Integration** | Integrate OpenAI/Anthropic/Gemini API. |
| **Prompt Engineering** | System prompt must be: "You are an expert corporate trainer. The user is currently studying \[Node Topic\]. Keep answers concise." |
| **Chat History** | Persist chat history per node or per session. |


  


### **3.4 Module D: L\&D Administration & Assignment**

**Goal:** Management needs to assign paths and see results.

* **Assignment:** Admin selects a User (or Team) and assigns "Backend Roadmap v1."  
* **Analytics Dashboard:**  
  * Table showing: Employee Name | Assigned Roadmap | % Complete | Last Active.  
  * Skill Gap: "50% of the Frontend Team hasn't started the 'TypeScript' node."

| Feature | Requirement Detail |
| :---- | :---- |
| **Assignment Logic** | Database relationship connecting User \<-\> Roadmap with status. |
| **Reporting** | Aggregate completion data. |


# 

# **4\. System Architecture & NFRs**

### **4.1 Non-Functional Requirements**

1. **Scalability:** The Roadmap schema must support deep nesting (e.g., 5-6 levels deep).  
2. **Performance:** Loading a roadmap with 50+ nodes must be instantaneous (\<500ms).  
3. **Security:** Users cannot mark nodes "Done" for roadmaps they aren't assigned to.

### **4.2 Technical Constraints**

* **Frontend:** React (Flow or React-Flow libraries allowed but custom implementation preferred for points), Vue, or Angular.  
* **Backend:** Node.js, Python, or Go.  
* **Database:** PostgreSQL (Recursive CTEs recommended for SQL) or MongoDB (Graph/Tree patterns).



# **5\. User Roles**

| Role | Permissions |
| :---- | :---- |
| **Learner** | View Assigned Roadmap, Click Nodes, Chat with AI, Mark Done, Earn XP. |
| **L\&D Admin** | Create Roadmaps (define nodes), Assign Roadmaps, View Analytics. |
| **Manager** | View Team Progress (Read-only). |



# **6\. Evaluation Summary**

### **Total Scoring Matrix**

| Section | Component | Points Available |
| :---- | :---- | :---- |
| **Module A** | User Profile & Gamification | 20 |
| **Module B** | Interactive Roadmap Engine | 25 |
| **Module C** | AI Tutor Integration | 20 |
| **Module D** | L\&D Admin & Analytics | 10 |
| **Arch** | DB Schema (Graphs) & Security | 20 |
| **Bonus** | **See Below** | **\+15** |
| **Total** | **Max Score** | **110** |

### 

### **Bonus Challenges (The "Wow" Factor)**

1. **AI Roadmap Generator:** Allow the Admin to type "Create a roadmap for Senior Java Developer" and use the LLM to generate the JSON node structure automatically. **(+10 Points)**  
2. **Strict Mode:** Prevent a user from marking a node as "Done" until they pass a mini 3-question quiz generated by the AI for that specific node. **(+5 Points)**

# 

# **7\. Submission Instructions**

1. **Repo:** Private GitHub repository.  
2. **Documentation:** README.md explaining:  
   * **The "Tree/Graph" strategy:** How did you store the roadmap data? (Adjacency list, Nested Sets, Materialized Path?).  
   * **Prompt Strategy:** How did you make the AI behave like a tutor?  
3. **Deadline:** 6 hours  
   

