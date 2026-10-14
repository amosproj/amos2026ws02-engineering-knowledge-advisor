# Bosch Project — Engineering Knowledge Database

<aside>
📌

Session-based description from the project pitch and Q&A on October 7, 2026. This page records what was discussed, not a proposed architecture or an agreed implementation specification. Possibilities and unresolved points remain marked as such.

</aside>

Source: Bosch presentation by Tobias Kober and the subsequent discussion.

## 1. Industrial context

Bosch’s Special Purpose Machinery department in Nuremberg builds fully automated machines, including systems with robots, and delivers them to customers worldwide. Its work spans mechanical design, electrical design, and PLC software controlling machine logic. Customers come from several industries, including automotive, chemicals, and aerospace.

Tobias emphasized that this department approaches the project from the **hardware and industrial engineering side**, rather than as a software company. Bosch brings the machines, construction data, and engineering expertise; the student team needs to translate that domain problem into software requirements. [[1]](https://app.notion.com/p/Project-Pitches-3f28b1de4bd880cea040ca1cebb3742a?pvs=21)

## 2. The problem: designs exist, but the reasoning remains in people’s heads

The department has built machines for decades and holds many existing modules, structured files, and engineering solutions. However, the files alone do not explain everything needed to understand or reuse those solutions.

Experienced designers know why a particular solution was chosen, which alternatives worked poorly, and how a machine actually behaves. Tobias specifically distinguished the information in the model from knowledge about machine function, cycle times, movements, and logic, which engineers must explain.

An approaching wave of retirements makes this urgent: Bosch risks losing the knowledge behind its accumulated designs. Tobias described this as a wider industrial problem, not something unique to Bosch. The aim is to retain that knowledge and make it available to subsequent generations of engineers. [[1]](https://app.notion.com/p/Project-Pitches-3f28b1de4bd880cea040ca1cebb3742a?pvs=21)

## 3. Project objective

The central idea is an **engineering knowledge database that links existing mechanical design data with the knowledge of the designers who developed those solutions**.

The database should support reuse of engineering solutions by newer engineers and colleagues, including those working on the PLC side. Bosch wants a starting point that can grow over time, rather than treating knowledge preservation as a problem that will be completely solved within one semester.

Tobias repeatedly emphasized that **linking human knowledge to engineering data is the main task**. A chat function was discussed as a user interface, but it was not the primary objective or necessarily the first implementation step.

## 4. How this relates to Bosch’s current work

### Handling a new machine request

Customers often provide incomplete information: they arrive with an idea and ask Bosch to build a machine. Experienced employees draw on earlier projects to decide how to approach it.

Tobias gave the example of a **robot gripping system**. An experienced engineer remembers having built several versions over previous decades, knows which performed well or poorly, and selects a suitable earlier solution. Today, much of that selection process happens in the engineer’s head. The project should help transfer this experience into a reusable digital form.

Bosch must ultimately deliver physical machines within cost and delivery-date constraints. However, Tobias clarified that this project’s emphasis is **preserving distinctive engineering knowledge and differentiating Bosch from competitors**, rather than primarily optimizing cost or time.

### Internal use, not customer interviewing

Yan asked whether the tool would help Bosch understand an incoming request internally or extract more information directly from customers. Tobias explained that extracting customer knowledge and optimizing the customer-request process are addressed by other Bosch initiatives. This project focuses on Bosch’s own engineering knowledge and its internal reuse.

## 5. Functionality and output discussed

### Finding relevant previous solutions

Tobias described a possible initial result: an engineer enters a request for a **gripper solution for a part approximately five centimetres in size**, and the software identifies earlier machines containing relevant gripping solutions, potentially displaying the models themselves.

He said that this could be enough at the beginning. A more elaborate chatbot would be a second or third step, rather than the prerequisite for useful software.

### Human-readable representation

When asked whether the information should be represented as a graph, an image, or a semantic model, Tobias expressed interest in a graph-like or visual output. His main criterion was that a human should be able to understand what is shown. The meeting did not establish a specific representation or database technology as mandatory.

### Reasons behind design changes

A student asked whether the system should preserve the reasons for changes to a component—for example, changes arising from customer requirements or technical problems—so that a replacement engineer can understand earlier decisions after an experienced colleague retires. Tobias agreed that this belongs to the knowledge-preservation objective. No detailed change-history implementation was specified.

## 6. Knowledge capture and interaction with experts

Bosch offered interaction with its designers and engineering colleagues, not only access to documents. Designers would answer questions about particular models and participate in interviews.

The instructor clarified an important boundary: **the student team should not spend the entire project manually interviewing Bosch experts**. Interviews during the project should support initial understanding and testing. The software should help later users document interviews and get expert knowledge into the database.

This makes knowledge capture part of the software challenge, not merely a one-off data-gathering activity performed by students. A specific interview interface or automated interviewing approach was not agreed during the session.

## 7. Data, formats, and system access

- **Construction data:** Bosch said it could share selected construction files and provide access to the engineers who understand them.
- **Design software:** Tobias referred to the department’s construction software as “AutoCAD Inventor.”
- **Formats mentioned in the session notes:** STEP, IAM, and JT. Tobias said the team could focus on a single format, depending on the information it contains.
- **Metadata:** Richer metadata would help the team understand the parts and models. Tobias also noted that the files contain substantial part history.
- **Parsing:** No parsing framework was prescribed. Reading the structured files was discussed, but Tobias regarded linking those files to human understanding as the harder problem.
- **Direct CAD integration:** An API exists, but Tobias was uncertain whether direct integration would be too complicated because of licensing. Exported files were discussed as an alternative.
- **Restricted access:** Bosch would not provide unrestricted access to its full engineering knowledge. A smaller database or selected data corpus was discussed.
- **MCP availability:** A student asked whether the CAD/data system had an MCP server. Tobias could not confirm this and said he needed to check. The instructor noted that the student team could potentially implement a tools interface over supplied data.
- **Production connection:** Tobias explicitly said that full connection to Bosch’s system would be needed later, but would **not be part of this student project**.

## 8. Technical freedom, collaboration, and validation

**Technology choices:** Bosch did not mandate a particular framework or stack. The team was free to discuss and try technologies with Bosch. No finished software architecture was confirmed in the discussion.

**Domain knowledge:** Students do not need to be mechanical or electrical engineers or design new machines themselves. Tobias asked for interest in understanding the models, data, and physical machinery, with a hands-on attitude.

**Product ownership:** The instructor highlighted the need for strong product owners/product managers who listen to Bosch’s engineers, understand their needs, and translate them into software development requirements. Bosch would be more hands-off technically than some other project partners, but engineering colleagues would be available for discussion.

**Language:** Tobias noted that English might pose some challenges for engineering colleagues, but expected these to be manageable.

**Validation:** When asked how the team would establish correctness, Tobias pointed to Bosch engineers with around 25 years of experience. They can judge whether a proposed machine solution would work. No formal benchmark or numerical acceptance threshold was defined during the pitch.

## 9. Boundaries and unresolved points from the meeting

| Topic | Status stated during the session |
| --- | --- |
| Core objective | Link mechanical design data with experienced designers’ knowledge for later reuse. |
| Initial useful result | Retrieving relevant earlier gripper solutions and possibly their models was given as an example, not a fixed deliverable. |
| Chatbot | A possible later step; not the core first task. |
| Graph/visual output | Discussed as a direction; exact representation remained open. |
| Technology stack | Open to team discussion with Bosch. |
| Data corpus | Selected Bosch data needed; exact contents and access arrangements remained to be settled. |
| MCP server | Availability to be checked by Bosch; not confirmed. |
| Direct CAD API connection | Licensing/complexity concerns raised; not confirmed as the approach. |
| Full integration with Bosch systems | Deferred beyond this student project. |
| Expert interviews | Available for understanding and testing; software should support later knowledge capture. |
| Semester scope | To be developed through requirements and prioritization within the available course time. |

The instructor reiterated that AMOS is time-based rather than tied to a fixed, fully specified deliverable, while still expecting useful software. Both Bosch and the instructor expressed interest in taking the work beyond AMOS with interested students; no concrete continuation arrangement was announced.
