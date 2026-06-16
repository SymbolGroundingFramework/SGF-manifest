# Omega Formal Grammar Specification v1.0 Final Candidate

File: 03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md  
Layer: OMEGA (governance grammar)  
Status: Final Candidate

## 0. Relationship to the Omega spec family

This document is the formal grammar and lexical specification for Omega-Code. It is part of the Omega specification family:

- 03-OMEGA-01_LANGUAGE_SPEC.md  
  Omega language model, primitive set, profiles, evaluator obligations, and integration with SGF/HFF/AFP.

- 03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md  
  (This file.) Canonical lexical structure, EBNF notation, keyword set, formal grammar, and operational semantics for all 13 primitives.

- 03-OMEGA-03_IMPLEMENTERS_GUIDE.md  
  Required static and runtime checks, profile enforcement, determinism, and evaluator behavior.

- 03-OMEGA-04_EXTENSION_GOVERNANCE.md  
  Governance of Omega extensions, Constitutional tier, and extension ratification and revocation procedures.

The books in the `books/` folder explain the concepts. The `03-OMEGA-*` files in `specs/` are the canonical home of the Omega language specification.

---

## A.1 Purpose and Scope

This appendix is the formal reference for Omega-Code, the pseudocode meta-language introduced in Chapter 4 and employed throughout this volume to specify self-governing autonomous systems. It provides every implementer, verification engineer, or specification author with the complete syntax, grammar, and operational semantics needed to write, parse, and verify Omega-Code without consulting any other document.

Two profiles are formally defined here. The Strict Profile is suitable for policy-evaluation slots whose decidability must be guaranteed at specification time. The Extended Profile admits the full pseudocode meta-language and is appropriate wherever bounded general computation is required. The PROFILE directive declares the default profile for the compilation unit before modules or top-level statements. Every section that follows is annotated with [STRICT], [EXTENDED], or [BOTH] to indicate which profile admits that construct.

Two documented defects from prior drafts of the Reference Manual are corrected in this appendix. The corrections are applied directly in the grammar and in the relevant primitive sections, and each is accompanied by a footnote.

---

## A.2 The Two Profiles

Omega-Code supports two formally defined operational profiles.

### A.2.1 Strict Profile [STRICT]

The Strict Profile admits, inside policy-evaluation slots, only the following constructs: Boolean expressions, comparison operations, set-membership tests, observation lookups, and calls to registered Strict predicate functions. A registered Strict predicate function must be pure, total over its declared input types, deterministic, side-effect-free, non-recursive, terminating by construction, and limited to declared observation inputs. No LOOP, no general recursion, no mutable state, no external I/O, no unregistered host calls, and no user-defined FUNCTION are permitted inside a Strict-profile policy slot. All Strict-profile specifications are statically decidable.

### A.2.2 Extended Profile [EXTENDED]

The Extended Profile admits the full pseudocode meta-language inside policy slots: IF, LOOP WHILE, LOOP FOR, FUNCTION definitions, and recursion. Any Extended-profile policy-evaluation slot that uses Extended-only constructs must declare a governing CONSTRAINT_SET of one or more RESOURCE_BOUND identifiers. If evaluation exceeds a declared bound, the result is UNKNOWN rather than an error; the calling context must handle UNKNOWN as a defined third value.

### A.2.3 Profile Declaration [BOTH]

The PROFILE directive appears at compilation-unit level, before modules or top-level statements:

```omega
PROFILE Strict;
```

or

```omega
PROFILE Extended;
```

If no PROFILE directive is present, the specification is assumed to operate under the Strict Profile.

---

## A.3 Lexical Structure [BOTH]

An Omega-Code specification is a sequence of tokens. The primary token categories follow.

### A.3.1 Identifiers [BOTH]

Identifiers are used for names of modules, functions, variables, and all unique IDs (for example, ContextID, EntityID, RuleID). An identifier must begin with a letter (a-z, A-Z) and may be followed by any number of letters, digits (0-9), or underscores (_). Identifiers are case-sensitive and cannot be identical to any reserved keyword.

Formal EBNF:
```ebnf
Identifier ::= <Letter> { <Letter> | <Digit> | '_' }
Letter ::= 'a' | ... | 'z' | 'A' | ... | 'Z'
Digit  ::= '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9'
```

### A.3.2 Keywords [BOTH]

Keywords are reserved words with special meaning in the language. They are always written in uppercase. The 13 atomic primitive names (CONTEXT_RULE, TEMPORAL_RELATION, RESOURCE_BOUND, ENVIRONMENT_INTERFACE_POINT, DATA_TYPE_SCHEMA, STATE_TRANSITION, TRUST_ELEMENT, GOVERNANCE_RULE, SELF_REFERENCE_POINT, MUTATION_RULE, PERCEPTION_MAP, LEARNING_AXIOM, META_DEFINITION_RULE) are keywords. The inherent-feature keywords MODULE, IF, THEN, ELSE, LOOP, WHILE, FOR, IN, FUNCTION, RETURNS, DECLARE, VAR, RETURN, BREAK, CONTINUE, AND, OR, NOT, END MODULE, END IF, END LOOP, END FUNCTION, ASSIGN, TO, AS are also keywords. The complete list appears in Section A.8.

### A.3.3 Literals [BOTH]

**Boolean literals:** TRUE, FALSE

**Integer literals:** Sequences of decimal digits, for example 123, 0, 42.

**Float literals:** An integer literal followed by a decimal point followed by another integer literal, for example 3.14, 0.5.

**String literals:** Any Unicode character sequence enclosed in straight double-quote characters ("), for example "hello world". The double-quote character itself may not appear unescaped inside a string literal.

Formal EBNF:
```ebnf
Literal        ::= 'TRUE' | 'FALSE' | <IntegerLiteral> | <FloatLiteral> | <StringLiteral>
IntegerLiteral ::= <Digit> { <Digit> }
FloatLiteral   ::= <IntegerLiteral> '.' <IntegerLiteral>
StringLiteral  ::= '"' { <CharInString> } '"'
CharInString   ::= (* any Unicode character except '"' *)
```

### A.3.4 Operators [BOTH]

- Arithmetic: `+`, `-`, `*`, `/`
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Logical: `AND`, `OR`, `NOT` (unary)

### A.3.5 Delimiters and Punctuation [BOTH]

- `( )` parentheses for grouping expressions and function arguments
- `{ }` curly braces for zero-or-more repetitions in EBNF; also for set literals in pseudocode
- `[ ]` brackets for optional elements in EBNF notation
- `,` comma for separating elements in parameter lists
- `:` colon for type declarations and parameter separation within primitive calls
- `;` semicolon to terminate statements

### A.3.6 Comments [BOTH]

**Line comments:** Begin with `--` and extend to the end of the line.

**Block comments:** Begin with `(*` and end with `*)`. May span multiple lines.

Formal EBNF:
```ebnf
Comment      ::= BlockComment | LineComment
BlockComment ::= '(*' { <CharInComment> } '*)'
LineComment  ::= '--' { <CharInComment> } <Newline>
Newline      ::= '\n' | '\r\n' | '\r'
CharInComment ::= (* any Unicode character except newline, or '*' followed by ')' for BlockComment *)
```

---

## A.4 EBNF Notation Conventions

This appendix uses the following Extended Backus-Naur Form (EBNF) notation throughout.

- `::=` means "is defined as" or "consists of"
- `|` means "or" and separates alternatives
- `[ item ]` denotes an optional item (zero or one occurrence)
- `{ item }` denotes an item that may be repeated zero or more times
- `( item1 item2 )` denotes a grouping of items
- `'literal'` denotes a terminal symbol that must appear exactly as shown
- `<non_terminal>` denotes a non-terminal symbol defined by another rule
- `(* comment *)` denotes a comment within the EBNF grammar itself

---

## A.5 Inherent Language Features

The following capabilities are intrinsic to Omega-Code. They provide the scaffolding upon which the 13 atomic primitives operate.

### A.5.1 Syntax and Grammars [BOTH]

**Purpose:** Omega-Code possesses a formally defined syntax and sanctioned extensibility points. This ensures the language is unambiguous and machine-readable, which is essential for automated processing and formal verification. The core parser productions are Constitutional; META_DEFINITION_RULE extends only sanctioned vocabulary categories and composition patterns outside that core.

**EBNF Syntax:** The grammar is rooted at `<OmegaCode>`. See Section A.10 for the complete grammar.

**Semantics:** Any valid Omega-Code specification must conform to the EBNF rules defined in this appendix. The processing system (parser) will accept only inputs that are parsable according to this grammar. META_DEFINITION_RULE does not rewrite the Constitutional parser productions; it operates on the extensible categories admitted by those productions.

### A.5.2 Basic Control Flow [EXTENDED ONLY]

**Purpose:** Provides core constructs for sequential execution, conditional branching (IF/ELSE), and iterative execution (LOOP). These constructs are admitted only under the Extended Profile inside policy-evaluation slots. They may appear in non-policy scaffolding where the grammar admits them, but they must not be reachable from a Strict policy-evaluation slot.

**EBNF Syntax:**
```ebnf
IfStatement   ::= 'IF' <BooleanExpression> 'THEN' <Block> [ 'ELSE' <Block> ] 'END IF' [ ';' ]
LoopStatement ::= 'LOOP' ( 'WHILE' <BooleanExpression> | 'FOR' <VariableName> 'IN' <Range> ) <Block> 'END LOOP' [ ';' ]
Range         ::= <Expression> 'TO' <Expression> | <Identifier>
```

**Semantics:**

- IF: Evaluates `<BooleanExpression>`. If TRUE, executes the THEN `<Block>`. If FALSE and ELSE is present, executes the ELSE `<Block>`. Otherwise execution continues with the next statement.
- LOOP WHILE: Continuously evaluates `<BooleanExpression>`. If TRUE, executes `<Block>`. Repeats until the expression is FALSE.
- LOOP FOR: Iterates `<VariableName>` through each item in `<Range>`. For each item, executes `<Block>`.
- BREAK: Immediately exits the innermost LOOP statement.
- CONTINUE: Skips the remainder of the current iteration of the innermost LOOP and proceeds to the next iteration.
- Statements execute sequentially in the order they appear.

### A.5.3 Function/Procedure Definition [EXTENDED ONLY]

**Purpose:** Enables modularity, abstraction, and reusability of logic by encapsulating named blocks of computation.

**EBNF Syntax:**
```ebnf
FunctionDefinition ::= 'FUNCTION' <FunctionName> '(' [ <ParameterList> ] ')' [ 'RETURNS' <ReturnType> ] <Block> 'END FUNCTION' [ ';' ]
FunctionName       ::= <Identifier>
ParameterList      ::= <Parameter> { ',' <Parameter> }
Parameter          ::= <ParameterName> ':' <DataType>
ParameterName      ::= <Identifier>
ReturnType         ::= <DataType> | 'VOID'
```

**Semantics:** Defines a named, callable block of logic. Parameters are passed by value. A function with a RETURNS type must terminate with a RETURN statement providing a value of that type. A function without RETURNS (or with RETURNS VOID) need not include a RETURN statement.

### A.5.4 Variable Declaration and Scoping [BOTH]

**Purpose:** Provides mechanisms for defining, storing, and managing data with a clear lifecycle.

**EBNF Syntax:**
```ebnf
VariableDeclaration ::= ( 'DECLARE' | 'VAR' ) <VariableName> [ ':' <DataType> ] [ 'AS' <InitialValue> ]
VariableName        ::= <Identifier>
InitialValue        ::= <Expression>
```

**Semantics:** DECLARE or VAR creates a new mutable, lexically scoped variable. Variables are visible only within the block they are declared in and its nested blocks. If AS `<InitialValue>` is provided, the variable is initialized with that value. If no initial value is provided, the variable receives a type-appropriate default: FALSE for BOOLEAN, 0 for INTEGER and FLOAT, and "" for STRING. Variables are mutable by default.

Note: VariableDeclaration is a SimpleStatement and must be terminated by a semicolon (`;`). See Section A.10 and its footnote for the corrected grammar classification.

### A.5.5 Module/Namespace System [BOTH]

**Purpose:** Provides hierarchical organization for large specifications, preventing naming conflicts and enabling modular design.

**EBNF Syntax:**
```ebnf
ModuleDefinition ::= 'MODULE' <ModuleName> <Block> 'END MODULE' [ ';' ]
ModuleName       ::= <Identifier>
```

**Semantics:** Modules define named organizational units. Identifiers declared within a module are scoped to that module. Modules can be nested. The v1.0 canonical grammar uses local identifiers for named references. Host implementations may maintain namespace metadata internally, but dot-qualified reference syntax is not part of the v1.0 core grammar.

### A.5.6 Primitive Data Types [BOTH]

**Purpose:** Fundamental data representations are natively supported, forming the basis for all information within a specification.

**EBNF Syntax:**
```ebnf
DataType ::= 'BOOLEAN' | 'INTEGER' | 'FLOAT' | 'STRING' | <SchemaID> | <Identifier>
Literal  ::= 'TRUE' | 'FALSE' | <IntegerLiteral> | <FloatLiteral> | <StringLiteral>
```

**Semantics:**

- BOOLEAN: Represents truth values TRUE and FALSE.
- INTEGER: Represents whole numbers, for example 1, 100, -5.
- FLOAT: Represents real numbers with decimal points, for example 3.14, 0.0, -2.5.
- STRING: Represents sequences of characters, for example "hello world" and "".
- Complex types are defined using DATA_TYPE_SCHEMA (see Section A.6.5).

### A.5.7 Inherent Actions/Operations [BOTH]

**Purpose:** Predefined, atomic operation descriptors registered by the host execution environment. They are invoked via ActionCalls or referenced by ActionIDs inside primitive calls. They represent host-bound computational or interaction behaviors available to the Safety Kernel for authorization and reporting; Omega itself does not execute physical effects.

**EBNF Syntax:**
```ebnf
ActionCall ::= <ActionID> '(' [ <ArgumentList> ] ')'
ActionID   ::= <Identifier>
```

**Semantics (representative examples):**

- `INCREMENT_ACTION(<Variable>)`: Increments an integer or float variable by 1.
- `DECREMENT_ACTION(<Variable>)`: Decrements an integer or float variable by 1.
- `LOG_ACTION(<Expression>)`: Records the value of the expression to a system log.
- `SEND_MESSAGE_ACTION(<RecipientID>, <MessageContent>)`: Sends a message to a specified recipient.
- `HYDRATE_DATA_ACTION(<ExternalDataRef>, <SchemaID>)`: Binds host-provided external data to a structured data object conforming to a schema.
- `ADJUST_THRESHOLD_BY_FACTOR(<BoundID>, <Factor>)`: Modifies the threshold of a RESOURCE_BOUND.
- `EXTRACT_TAGGED_CONTENT(<Text>, <Tag>)`: Extracts content from tagged text.

This list is illustrative. Additional actions may be defined and registered for specific implementation environments. Every ActionID referenced by STATE_TRANSITION, MUTATION_RULE, or PERCEPTION_MAP must resolve at load time to a host action descriptor or declared abstract action in the conformance environment. A descriptor minimally declares the action name, argument signature, return type if any, side-effect class, determinism class, permitted profile or profiles, and resource-bound behavior.

---

## A.6 The 13 Atomic Core Primitives

The following sections provide the complete formal definition for each of the 13 atomic core primitives: purpose, formal EBNF syntax, formal semantics, profile applicability, and a concrete example.

The 13 primitives separate into two groups by what they operate on. Nine are object-primitives: CONTEXT_RULE, TEMPORAL_RELATION, RESOURCE_BOUND, ENVIRONMENT_INTERFACE_POINT, DATA_TYPE_SCHEMA, STATE_TRANSITION, TRUST_ELEMENT, PERCEPTION_MAP, and LEARNING_AXIOM. They specify the system being modeled, its environment, and its data. Four are meta-primitives: GOVERNANCE_RULE, SELF_REFERENCE_POINT, MUTATION_RULE, and META_DEFINITION_RULE. They operate on rules and on the specification itself. GOVERNANCE_RULE governs which rules may fire. SELF_REFERENCE_POINT names elements of the specification as addressable targets. MUTATION_RULE governs how those targets may change. META_DEFINITION_RULE governs how the language's own extensible vocabulary may be enlarged. The split is not annotation. It is a structural fact about what each primitive's arguments range over: object-primitives quantify over the modeled system; meta-primitives quantify over rules, references, mutations, and definitions within the specification.

---

### A.6.1 CONTEXT_RULE [BOTH]

**Purpose:** Defines a formal context for reasoning, specifying its modalities (for example, Temporal, Probabilistic, Normative) and its tolerance for logical inconsistency. It establishes a named boundary that dictates how subsequent statements within that context are interpreted. ModalityTypes are extensible via META_DEFINITION_RULE.

**Formal EBNF Syntax:**
```ebnf
ContextRuleCall ::= 'CONTEXT_RULE' <ContextID> ':' 'MODALITY' '{' <ModalityType> { ',' <ModalityType> } '}' [ ',' 'INCOHERENCE_TOLERANCE' <Expression> ] [ ',' 'PARENT_CONTEXT' <ContextID> ]
ModalityType    ::= <Identifier>
ContextID       ::= <Identifier>
```

**Formal Semantics:** Establishes a named contextual boundary. MODALITY defines the nature of the context; valid values include Temporal, Probabilistic, Deterministic, Normative, and Ethical, among others extensible via META_DEFINITION_RULE. INCOHERENCE_TOLERANCE specifies the acceptable degree of logical contradiction within this context before a warning or failure is triggered. If omitted, the tolerance defaults to 0 (no contradiction permitted). PARENT_CONTEXT, if specified, declares this context as a child of the named parent. A child context inherits all GOVERNANCE_RULEs whose SCOPE matches the parent ContextID; the child's own MODALITY and INCOHERENCE_TOLERANCE override the parent's where they differ.

**Profile:** [BOTH]. The predicate slots within this primitive require only Boolean expressions, so it is statically decidable under both profiles.

**Concrete Example:**
```omega
CONTEXT_RULE RealtimeControlContext :
    MODALITY { Temporal, Deterministic }
    INCOHERENCE_TOLERANCE 0.01;
-- 1% tolerance for timing jitter in real-time control loops.

CONTEXT_RULE EthicalDecisionSpace :
    MODALITY { Normative, Probabilistic };
```

---

### A.6.2 TEMPORAL_RELATION [BOTH]

**Purpose:** Asserts a fundamental temporal ordering or relationship between two entities or events, for example BEFORE, AFTER, OVERLAPS, or CONTAINS. This is essential for defining causality, synchronization, and real-time planning constraints. TemporalRelationTypeID and IntervalDefinitionID are extensible via META_DEFINITION_RULE.

**Formal EBNF Syntax:**
```ebnf
TemporalRelationCall ::= 'TEMPORAL_RELATION' <RelationID> ':' 'SUBJECT_A' <EntityID> ',' 'SUBJECT_B' <EntityID> ',' 'TYPE' <TemporalRelationTypeID> [ ',' 'INTERVAL_A' <IntervalDefinitionID> ] [ ',' 'INTERVAL_B' <IntervalDefinitionID> ]
RelationID             ::= <Identifier>
TemporalRelationTypeID ::= <Identifier>
IntervalDefinitionID   ::= <Identifier>
```

**Formal Semantics:** Asserts that a specific temporal relationship (TYPE) holds between SUBJECT_A and SUBJECT_B. Examples of TemporalRelationTypeID are BEFORE, AFTER, OVERLAPS, and CONTAINS. INTERVAL_A and INTERVAL_B define specific time durations or points associated with each subject. When INTERVAL fields are present, the relation is evaluated with respect to those intervals rather than the instantaneous occurrence of the subjects.

**Profile:** [BOTH]. No loop or recursion appears in this primitive.

**Concrete Example:**
```omega
TEMPORAL_RELATION ProcessOrderBeforeShipment :
    SUBJECT_A OrderProcessing,
    SUBJECT_B ShipmentDispatch,
    TYPE BEFORE;

TEMPORAL_RELATION SensorReadingInterval :
    SUBJECT_A TemperatureSensorData,
    SUBJECT_B SystemLogEntry,
    TYPE OVERLAPS,
    INTERVAL_A CurrentSecond;
```

---

### A.6.3 RESOURCE_BOUND [BOTH]

**Purpose:** Declares a formal, quantifiable limit on a resource (for example, memory, CPU cycles, API calls) associated with a specific entity. If the declared threshold is exceeded, a named violation policy is invoked. ResourceTypeID and MetricID are extensible via META_DEFINITION_RULE. RESOURCE_BOUND also serves as the bounding mechanism for Extended-profile evaluation; an Extended-profile policy slot must reference a RESOURCE_BOUND in its CONSTRAINT_SET.

**Formal EBNF Syntax:**
```ebnf
ResourceBoundCall ::= 'RESOURCE_BOUND' <BoundID> ':' 'SUBJECT' <EntityID> ',' 'TYPE' <ResourceTypeID> ',' 'METRIC' <MetricID> ',' 'THRESHOLD' <NumericExpression> ',' 'VIOLATION_POLICY' <PolicyID>
BoundID          ::= <Identifier>
ResourceTypeID   ::= <Identifier>
MetricID         ::= <Identifier>
PolicyID         ::= <Identifier>
```

**Formal Semantics:** Specifies that SUBJECT is limited in its consumption or availability of a resource of the given TYPE, measured by METRIC, not exceeding THRESHOLD. If THRESHOLD is violated, the named VIOLATION_POLICY is invoked. Example violation policies are LOG_ERROR, HALT_PROCESS, TRIGGER_ALERT, and ThrottleRequests. Under the Extended Profile, if evaluation of a policy slot would exceed its governing RESOURCE_BOUND, the result is UNKNOWN.

**Profile:** [BOTH]. The declaration itself is statically decidable; bounded Extended-profile evaluation uses this primitive to establish the execution ceiling.

**Concrete Example:**
```omega
RESOURCE_BOUND MaxMemoryUsage :
    SUBJECT WebserverProcess,
    TYPE Memory,
    METRIC Megabytes,
    THRESHOLD 2048,
    VIOLATION_POLICY SendAlertToAdmin;

RESOURCE_BOUND MaxApiCallsPerMinute :
    SUBJECT LLMAgent,
    TYPE ApiCallRate,
    METRIC CallsPerMinute,
    THRESHOLD 60,
    VIOLATION_POLICY ThrottleRequests;
```

---

### A.6.4 ENVIRONMENT_INTERFACE_POINT [BOTH]

**Purpose:** Defines an atomic point of interaction between a system entity and an external entity or phenomenon, for example a sensor, an actuator, or a network socket. It specifies the nature of the interaction, the data format exchanged, and an optional uncertainty model for probabilistic or noisy channels. InteractionTypeID is extensible via META_DEFINITION_RULE.

**Formal EBNF Syntax:**
```ebnf
EnvironmentInterfacePointCall ::= 'ENVIRONMENT_INTERFACE_POINT' <InterfaceID> ':' 'SUBJECT' <EntityID> ',' 'EXTERNAL_REFERENT' <EntityID> ',' 'INTERACTION_TYPE' <InteractionTypeID> ',' 'DATA_SCHEMA' <SchemaID> [ ',' 'UNCERTAINTY_MODEL' <ModelID> ]
InterfaceID       ::= <Identifier>
InteractionTypeID ::= <Identifier>
SchemaID          ::= <Identifier>
ModelID           ::= <Identifier>
```

**Formal Semantics:** Designates a named interface where SUBJECT interacts with EXTERNAL_REFERENT. INTERACTION_TYPE describes the nature of the interaction; examples are ReadSensor, SendCommand, ReceiveMessage, and DisplayMessage. DATA_SCHEMA defines the expected format of information exchanged (referencing a DATA_TYPE_SCHEMA). An UNCERTAINTY_MODEL can be specified for interactions that are probabilistic or subject to noise.

**Profile:** [BOTH]. This is a declarative boundary specification with no loop or recursion.

**Concrete Example:**
```omega
ENVIRONMENT_INTERFACE_POINT TemperatureSensorInput :
    SUBJECT RoboticsSystem,
    EXTERNAL_REFERENT PhysicalEnvironment,
    INTERACTION_TYPE SensorRead,
    DATA_SCHEMA TemperatureDataSchema,
    UNCERTAINTY_MODEL GaussianNoiseModel;

ENVIRONMENT_INTERFACE_POINT UserCommandOutput :
    SUBJECT UserInterfaceModule,
    EXTERNAL_REFERENT HumanUser,
    INTERACTION_TYPE DisplayMessage,
    DATA_SCHEMA DisplayMessageSchema;
```

---

### A.6.5 DATA_TYPE_SCHEMA [BOTH]

**Purpose:** Provides the formal schema for defining new, structured data types and their intrinsic semantic properties (for example, PII, FinancialData, Encrypted). It is analogous to a struct or record definition and forms the basis for all complex information models in a specification. PropertyID is extensible via META_DEFINITION_RULE.

**Formal EBNF Syntax:**
```ebnf
DataTypeSchemaCall  ::= 'DATA_TYPE_SCHEMA' <SchemaID> ':' 'DEFINITION' <SchemaDefinition> [ 'SEMANTIC_PROPERTIES' '{' <PropertyID> { ',' <PropertyID> } '}' ]
SchemaDefinition    ::= '(' { FieldDefinition } ')'
FieldDefinition     ::= ( 'VAR' | 'FIELD' | 'PROPERTY' ) <FieldName> ':' <DataType> [ 'AS' <InitialValue> ] ';'
FieldName           ::= <Identifier>
PropertyID          ::= <Identifier>
```

**Formal Semantics:** Defines a reusable, named data structure. DEFINITION outlines its fields, their types, and optional default values. SEMANTIC_PROPERTIES allows tagging with meta-information about the data's intended meaning, enabling policy-layer reasoning about data categories without inspecting field values.

**Profile:** [BOTH]. DATA_TYPE_SCHEMA is a static declaration.

**Concrete Example:**
```omega
DATA_TYPE_SCHEMA TemperatureDataSchema :
    DEFINITION (
        VAR value : FLOAT;
        VAR unit : STRING AS "Celsius";
        VAR timestamp : STRING;
    );

DATA_TYPE_SCHEMA UserProfile :
    DEFINITION (
        VAR userId : INTEGER;
        VAR username : STRING;
        VAR email : STRING;
        VAR signupDate : STRING;
    )
    SEMANTIC_PROPERTIES { PII_IDENTIFIER, CONFIDENTIAL };
```

---

### A.6.6 STATE_TRANSITION [BOTH]

**Purpose:** Defines an atomic, conditional authorization for a host state change. It specifies the precondition that must hold before the host action may be authorized, the action descriptor itself, and the postcondition to verify after the host reports completion. An optional reversion protocol names host remediation behavior; it is not a guarantee of physical rollback.

**Formal EBNF Syntax:**
```ebnf
StateTransitionCall ::= 'STATE_TRANSITION' <TransitionID> ':' 'SUBJECT' <EntityID> ',' 'PRECONDITION' <BooleanExpression> ',' 'POSTCONDITION' <BooleanExpression> ',' 'ACTION' <ActionID> [ ',' 'REVERSION_PROTOCOL' <ProtocolID> ] [ ',' 'AUTHORIZED_BY' <ElementID> ] ',' 'GOVERNED_BY' <RuleID> [ ',' 'CONSTRAINT_SET' <BoundIDList> ]
TransitionID        ::= <Identifier>
```

**Formal Semantics:** Describes a host action (ACTION) proposed against SUBJECT. PRECONDITION must evaluate to TRUE before the Safety Kernel may authorize the action. After the host reports completion, POSTCONDITION is the verification predicate the kernel or reporting layer evaluates; a false or unobservable postcondition is a structured reportable outcome, not proof that Omega guaranteed or physically executed the transition. REVERSION_PROTOCOL defines a host remediation protocol if needed and authorized. AUTHORIZED_BY, if specified, references the TRUST_ELEMENT that must hold for the transition to fire and that records the authorizing identity for audit. GOVERNED_BY is required and references the GOVERNANCE_RULE under whose authority the transition is permitted. Together, AUTHORIZED_BY and GOVERNED_BY make the transition's audit record structural rather than implicit: the specification declares who authorized the change and which rule permitted it. Under the Strict Profile, PRECONDITION and POSTCONDITION must be statically decidable Boolean expressions. Under the Extended Profile, Extended-only constructs in PRECONDITION, POSTCONDITION, or a transition-local evaluation slot require CONSTRAINT_SET, and each listed bound must resolve to a RESOURCE_BOUND at load time.

**Profile:** [BOTH]. PRECONDITION and POSTCONDITION complexity varies by profile.

**Concrete Example:**
```omega
GOVERNANCE_RULE AllowOrderProcessing :
    SCOPE ProcessOrder,
    PREDICATE ( StatusIsPending(CustomerOrder_123) ),
    ENFORCEMENT_MODE ALLOW_ACTION,
    PRIORITY 10;

STATE_TRANSITION ProcessOrder :
    SUBJECT CustomerOrder_123,
    PRECONDITION ( StatusIsPending(CustomerOrder_123) ),
    POSTCONDITION ( StatusIsProcessing(CustomerOrder_123) ),
    ACTION UpdateOrderStatusToProcessing,
    REVERSION_PROTOCOL RollbackOrderStatus,
    GOVERNED_BY AllowOrderProcessing;

GOVERNANCE_RULE AllowDoorUnlock :
    SCOPE UnlockDoor,
    PREDICATE ( IsLocked(SmartLock_A) AND UserAuthenticated(User_Alice) ),
    ENFORCEMENT_MODE ALLOW_ACTION,
    PRIORITY 10;

STATE_TRANSITION UnlockDoor :
    SUBJECT SmartLock_A,
    PRECONDITION ( IsLocked(SmartLock_A) AND UserAuthenticated(User_Alice) ),
    POSTCONDITION ( IsUnlocked(SmartLock_A) ),
    ACTION SendUnlockCommand,
    GOVERNED_BY AllowDoorUnlock;
```

---

### A.6.7 TRUST_ELEMENT [BOTH]

**Purpose:** Defines an atomic, verifiable assertion about one entity's relationship to or property concerning another. It specifies the subject, a Boolean predicate encoding the claim, the object of the claim, and an optional proof protocol for external verification. This primitive forms the basis for security, identity management, and distributed consensus specifications.

**Formal EBNF Syntax:**
```ebnf
TrustElementCall ::= 'TRUST_ELEMENT' <ElementID> ':' 'SUBJECT' <EntityID> ',' 'PREDICATE' <BooleanExpression> ',' 'OBJECT' <EntityID> [ ',' 'PROOF_PROTOCOL' <ProtocolID> ] [ ',' 'REVOCATION_PROTOCOL' <ProtocolID> ] [ ',' 'ACCOUNTABILITY_CHAIN' <ChainID> ]
ElementID        ::= <Identifier>
```

**Formal Semantics:** States a named verifiable assertion: SUBJECT (the identity bearer) has the relationship or property encoded in PREDICATE (the scope of the assertion) with respect to OBJECT. PROOF_PROTOCOL specifies how this assertion is validated externally; examples are DigitalSignature, OAuth2_Flow, and ZeroKnowledgeProof. REVOCATION_PROTOCOL, if specified, defines the named procedure by which the trust assertion may be invalidated before its natural expiration; examples are CertificateRevocationList, OCSP_Lookup, and AdministrativeRevocation. ACCOUNTABILITY_CHAIN, if specified, references a named chain of authorities responsible for actions taken under this trust assertion, supporting downstream attribution of consequences. The four optional and required slots together implement the four properties the prose chapters identify: identity (SUBJECT), scope (PREDICATE plus OBJECT), revocability (REVOCATION_PROTOCOL), and accountability (ACCOUNTABILITY_CHAIN). Under the Strict Profile, PREDICATE must be a statically decidable Boolean expression. Under the Extended Profile, PREDICATE may involve full bounded computation.

**Profile:** [BOTH]. PREDICATE complexity varies by profile.

**Concrete Example:**
```omega
TRUST_ELEMENT UserIdentityVerified :
    SUBJECT User_Bob,
    PREDICATE ( IsVerified(User_Bob) ),
    OBJECT AuthenticationService,
    PROOF_PROTOCOL OAuth2_Flow;

TRUST_ELEMENT DataIntegrityChecked :
    SUBJECT DatabaseRecord_X,
    PREDICATE ( HasValidChecksum(DatabaseRecord_X) ),
    OBJECT ChecksumVerificationSystem;
```

---

### A.6.8 GOVERNANCE_RULE [BOTH]

**Purpose:** Defines an atomic normative statement, which may be an obligation, a permission, or a prohibition, that governs system behavior within a specified scope. If the Boolean predicate evaluates to true, the named enforcement mode determines the response.

**Formal EBNF Syntax:**
```ebnf
GovernanceRuleCall ::= 'GOVERNANCE_RULE' <RuleID> ':' 'SCOPE' <ScopeID> ',' 'PREDICATE' <BooleanExpression> ',' 'ENFORCEMENT_MODE' <EnforcementModeID> [ ',' 'PRIORITY' <NumericExpression> ] [ ',' 'CONSTRAINT_SET' <BoundIDList> ]
ScopeID            ::= <Identifier>
EnforcementModeID  ::= <Identifier>
```

**Formal Semantics:** Specifies a named normative policy applying within SCOPE. If the rule's SCOPE does not match the proposed action, the rule contributes no verdict. If SCOPE matches and PREDICATE evaluates to FALSE, the rule contributes no verdict. If SCOPE matches and PREDICATE evaluates to TRUE, ENFORCEMENT_MODE names the enforcement response and must resolve at load time to exactly one mode class: permissive or prohibitive. The minimum conformant mode set is ALLOW_ACTION (permissive), LOG_ONLY (permissive), PREVENT_ACTION (prohibitive), and REQUIRE_HUMAN_APPROVAL (prohibitive unless approval is separately modeled as a declared observation or trust predicate). Unknown or unclassified modes are load-time errors. This field is an enforcement-mode identifier, not a CONTEXT_RULE reference. PRIORITY specifies precedence when multiple rules contribute verdicts; higher numeric values indicate higher precedence. Equal-priority conflicts resolve fail-closed by status order DENY > UNKNOWN > ALLOW. Equal-priority same-status ties use lexicographic RuleID only to choose the reported rule_id. If PRIORITY is omitted, the default value is 0. Under the Strict Profile, PREDICATE must be a statically decidable Boolean expression. Under the Extended Profile, Extended-only constructs in PREDICATE require CONSTRAINT_SET, and each listed bound must resolve to a RESOURCE_BOUND at load time.

**Profile:** [BOTH]. PREDICATE complexity varies by profile.

**Concrete Example:**
```omega
GOVERNANCE_RULE NoDataDeletionWithoutConsent :
    SCOPE UserManagement,
    PREDICATE ( AttemptToDeleteUserData(user_id) AND NOT ConsentIsGiven(user_id) ),
    ENFORCEMENT_MODE PREVENT_ACTION,
    PRIORITY 99;

GOVERNANCE_RULE LogHighRiskOperation :
    SCOPE SystemSecurity,
    PREDICATE ( IsHighRisk(operation_type) ),
    ENFORCEMENT_MODE LOG_ONLY;
```

---

### A.6.9 SELF_REFERENCE_POINT [BOTH]

**Purpose:** Defines a formal, addressable handle to an element within the system's own definition, for example its data schemas or active rule sets, enabling introspection and controlled self-modification. TargetTypeID is a Constitutional category; valid target types come from the grammar's fixed target-type registry and are not extensible via META_DEFINITION_RULE.

**Formal EBNF Syntax:**
```ebnf
SelfReferencePointCall ::= 'SELF_REFERENCE_POINT' <PointID> ':' 'TARGET_TYPE' <TargetTypeID> ',' 'ACCESS_PROTOCOL' <ProtocolID>
PointID       ::= <Identifier>
TargetTypeID  ::= <Identifier>
```

**Formal Semantics:** Creates a named reference (PointID) to a permitted part of the system's own meta-level. TARGET_TYPE specifies what kind of meta-level element is referenced; examples include DATA_SCHEMA_DEFINITION and GOVERNANCE_RULE_SET. Target types that address grammar primitives, parser/compiler elements, primitive declarations, Appendix D, or the Constitutional tier are reserved to the Constitutional registry and cannot be created by a loaded specification. ACCESS_PROTOCOL defines how to interact with this point; examples are READ_DEFINITION, MODIFY_DEFINITION, and QUERY_RUNTIME_STATE. SELF_REFERENCE_POINT is the target of MUTATION_RULE (see Section A.6.10).

**Profile:** [BOTH]. The declaration is static; its use by MUTATION_RULE may vary by profile.

**Concrete Example:**
```omega
SELF_REFERENCE_POINT MainGrammarDefinition :
    TARGET_TYPE GOVERNANCE_RULE_SET,
    ACCESS_PROTOCOL READ_DEFINITION;

SELF_REFERENCE_POINT UserPreferenceSchemaRef :
    TARGET_TYPE DATA_SCHEMA_DEFINITION,
    ACCESS_PROTOCOL MODIFY_DEFINITION;
```

---

### A.6.10 MUTATION_RULE [BOTH]

**Purpose:** Defines an atomic rule under which the system may formally and safely modify itself. The target of modification must be a named SELF_REFERENCE_POINT. An optional approval policy governs whether external consent or internal validation is required before execution.

**Formal EBNF Syntax:**
```ebnf
MutationRuleCall      ::= 'MUTATION_RULE' <RuleID> ':' 'TARGET_REFERENCE' <SelfReferencePointID> ',' 'CONDITION' <BooleanExpression> ',' 'TRANSFORM_ACTION' <ActionID> [ ',' 'APPROVAL_POLICY' <PolicyID> ] [ ',' 'CONSTRAINT_SET' <BoundIDList> ]
SelfReferencePointID  ::= <Identifier>
```

**Formal Semantics:** Specifies a named rule for self-modification. If CONDITION is TRUE, the TRANSFORM_ACTION (an ActionID referring to a host-registered transform action) is applied to the element referenced by TARGET_REFERENCE. TARGET_REFERENCE must name a SELF_REFERENCE_POINT. APPROVAL_POLICY governs whether this mutation requires external consent or passes internal checks before execution; examples are AutomatedInternalApproval and RequireHumanAuthorization. The loader constructs a mutation authority graph whose nodes are mutable definitions addressable through SELF_REFERENCE_POINT. A direct edge exists from each MUTATION_RULE to its TARGET_REFERENCE. Derived authority edges include any mutation that can alter another mutation rule, approval policy, trust requirement, target reference, or governing rule. The loader rejects cycles that allow a mutation path to weaken its own approval policy, expand its own target set, bypass its governing authority, or alter Constitutional targets. Under the Strict Profile, CONDITION must be a statically decidable Boolean expression. Under the Extended Profile, Extended-only constructs in CONDITION or TRANSFORM_ACTION require CONSTRAINT_SET, and each listed bound must resolve to a RESOURCE_BOUND at load time.

**Profile:** [BOTH]. CONDITION complexity varies by profile.

**Concrete Example:**
```omega
SELF_REFERENCE_POINT RESOURCE_BOUND_MAX_MEMORY_USAGE :
    TARGET_TYPE RESOURCE_BOUND_DEFINITION,
    ACCESS_PROTOCOL MODIFY_DEFINITION;

MUTATION_RULE AdaptiveResourceThreshold :
    TARGET_REFERENCE RESOURCE_BOUND_MAX_MEMORY_USAGE,
    CONDITION ( LowSystemMemory(current_memory_usage) ),
    TRANSFORM_ACTION ADJUST_THRESHOLD_BY_FACTOR,
    APPROVAL_POLICY AutomatedInternalApproval;
```

---

### A.6.11 PERCEPTION_MAP [BOTH]

**Purpose:** Defines the typed binding from a declared ENVIRONMENT_INTERFACE_POINT or host-hydrated substrate observation into structured internal concepts conforming to a DATA_TYPE_SCHEMA. It bridges the host perception substrate and the Safety Kernel's typed governance state. An optional uncertainty model records probabilistic or noisy observation provenance.

**Formal EBNF Syntax:**
```ebnf
PerceptionMapCall ::= 'PERCEPTION_MAP' <MapID> ':' 'INPUT_INTERFACE' <InterfaceID> ',' 'OUTPUT_SCHEMA' <SchemaID> ',' 'TRANSFORMATION_FUNCTION' <ActionID> [ ',' 'UNCERTAINTY_MODEL' <ModelID> ]
MapID             ::= <Identifier>
```

**Formal Semantics:** Defines a named typed observation binding. It takes a declared observation available through INPUT_INTERFACE, applies TRANSFORMATION_FUNCTION as a registered host/substrate binding, and maps the resulting typed value to OUTPUT_SCHEMA. Omega does not parse raw streams, run LLM inference, or interpret sensor noise inside the Safety Kernel. An UNCERTAINTY_MODEL may be specified to describe probabilistic or noisy observation provenance.

**Profile:** [BOTH]. TRANSFORMATION_FUNCTION is a named ActionID; complexity of the underlying action does not affect this primitive's classification.

**Concrete Example:**
```omega
PERCEPTION_MAP HydrateSensorObservation :
    INPUT_INTERFACE TemperatureSensorInput,
    OUTPUT_SCHEMA TemperatureDataSchema,
    TRANSFORMATION_FUNCTION HydrateTemperatureObservation,
    UNCERTAINTY_MODEL SensorErrorModel;

PERCEPTION_MAP BindLLMResponseObservation :
    INPUT_INTERFACE LLMResponseAPI,
    OUTPUT_SCHEMA StructuredThoughtSchema,
    TRANSFORMATION_FUNCTION HydrateStructuredThought;
```

---

### A.6.12 LEARNING_AXIOM [BOTH]

**Purpose:** Defines the formal contract for a learning process: what it consumes as input, what it produces as output, the metric it optimizes, the resource bounds it must respect, and the rule by which it integrates learned knowledge into the system. KnowledgeUpdateRule must reference a MUTATION_RULE in the same module.

**Formal EBNF Syntax:**
```ebnf
LearningAxiomCall ::= 'LEARNING_AXIOM' <AxiomID> ':' 'INPUT_SCHEMA' <SchemaID> ',' 'OUTPUT_SCHEMA' <SchemaID> ',' 'OBJECTIVE_METRIC' <MetricID> ',' 'CONSTRAINT_SET' <BoundIDList> ',' 'KNOWLEDGE_UPDATE_RULE' <MutationRuleID> [ ',' 'ROLLBACK_CONDITION' <BooleanExpression> ]
AxiomID           ::= <Identifier>
ResourceBoundID   ::= <Identifier>
MutationRuleID    ::= <RuleID>
```

**Formal Semantics:** Defines a named learning process. Input data must conform to INPUT_SCHEMA. Output data must conform to OUTPUT_SCHEMA. The learning process optimizes for OBJECTIVE_METRIC. It operates within CONSTRAINT_SET, which is a set of references to previously declared RESOURCE_BOUND instances. Knowledge integration is performed via KNOWLEDGE_UPDATE_RULE, which must be the ID of a MUTATION_RULE already declared in the same module. Learning-driven updates therefore pass through the mutation authority machinery. ROLLBACK_CONDITION, if specified, is a Boolean expression that, when evaluated to TRUE after a learning step, rejects or reverts the proposed mutation according to the referenced MUTATION_RULE's approval and remediation path.

**Profile:** [BOTH]. The primitive declaration is static. The KNOWLEDGE_UPDATE_RULE referenced may itself be Strict or Extended depending on its own declaration.

**Concrete Example:**
```omega
LEARNING_AXIOM AdaptUserTonePreference :
    INPUT_SCHEMA UserFeedbackSchema,
    OUTPUT_SCHEMA UpdatedToneModelSchema,
    OBJECTIVE_METRIC ToneAlignmentScore,
    CONSTRAINT_SET { CPU_Constraint, Memory_Constraint },
    KNOWLEDGE_UPDATE_RULE UpdateInternalToneModelRule;
```

---

### A.6.13 META_DEFINITION_RULE [BOTH]

**Purpose:** Enables the formal extension of sanctioned Omega-Code vocabulary categories, for example defining new ModalityTypes, ResourceTypeIDs, InteractionTypeIDs, MetricIDs, or PropertyIDs. This is the mechanism by which the language remains future-proof without requiring changes to the core parser. It cannot extend TargetTypeID or any category that addresses grammar primitives, parser/compiler elements, primitive declarations, Appendix D, or the Constitutional tier.

**Formal EBNF Syntax:**
```ebnf
MetaDefinitionRuleCall ::= 'META_DEFINITION_RULE' <RuleID> ':' 'TARGET_TYPE' <TargetTypeID> ',' 'DEFINITION_SCHEMA' <SchemaDefinition> ',' 'VALIDATION_PROTOCOL' <ProtocolID>
```

Note: Earlier versions of the Reference Manual contained a typo in Section 8 listing this field as `<DataSchemaID>`. The correct type is `<SchemaDefinition>`.

**Formal Semantics:** Specifies a named rule for extending a sanctioned vocabulary category or conceptual ontology. TARGET_TYPE names the extensible category being enlarged, for example RESOURCE_TYPE_ID, MODALITY_TYPE, INTERACTION_TYPE_ID, METRIC_ID, or PROPERTY_ID. TARGET_TYPE must not name TARGET_TYPE_ID or any Constitutional target category. DEFINITION_SCHEMA provides the inline structural definition (using SchemaDefinition notation) that any new instance of this type must conform to. VALIDATION_PROTOCOL ensures that new definitions meet required standards; examples are SchemaValidation and FormalLogicCheck.

**Profile:** [BOTH]. META_DEFINITION_RULE is a static declaration.

**Concrete Example:**
```omega
META_DEFINITION_RULE DefineNewResourceType :
    TARGET_TYPE RESOURCE_TYPE_ID,
    DEFINITION_SCHEMA (
        VAR name : STRING;
        VAR measurementUnit : STRING;
        VAR accuracyTolerance : FLOAT;
    ),
    VALIDATION_PROTOCOL SchemaValidation;
```

---

## A.7 Common Composition Patterns

Primitives are designed to be composed to model complex behaviors. The following patterns are the most commonly employed in this volume. Patterns A.7.2, A.7.4, and A.7.5 derive from Reference Manual Section 10. Patterns A.7.1 and A.7.3 are formalized in this appendix from the operational semantics of their constituent primitives; they have no antecedent in the Reference Manual or Tech-Spec but are entailed by the primitive definitions in those sources.

A note on named compositions and the size of the primitive set. Some operational patterns can be analyzed as compositions, but the thirteen primitives remain canonical syntax because removing any primitive leaves a named failure class without a first-class addressable form. MUTATION_RULE, in particular, is retained because self-modification must be targetable, auditable, and load-time checked as its own construct rather than reconstructed informally at each use site. Implementation desugaring does not make a primitive eliminable from the normative grammar.

### A.7.1 STATE_TRANSITION x TRUST_ELEMENT: Verified State Change

This composition is the formal basis for the MAST FM-3.1 and FM-3.2 requirements referenced in Chapter 20. A state transition must not fire unless a TRUST_ELEMENT assertion about the acting subject has been verified by the named proof protocol.

1. `TRUST_ELEMENT`: Asserts that the acting entity has the necessary authorization (e.g., IsAuthorized(Agent), ProofProtocol: DigitalSignature).
2. `STATE_TRANSITION`: References the trust assertion as part of its PRECONDITION via the inherent action `TrustHolds(<TrustElementID>)`, ensuring the transition fires only when the trust claim has been verified.

```omega
TRUST_ELEMENT AgentAuthorizedForStateChange :
    SUBJECT ControlAgent_01,
    PREDICATE ( IsAuthorized(ControlAgent_01, TargetSystem) ),
    OBJECT TargetSystem,
    PROOF_PROTOCOL DigitalSignature;

GOVERNANCE_RULE AllowTargetActivation :
    SCOPE ActivateTargetSystem,
    PREDICATE ( TrustHolds(AgentAuthorizedForStateChange) AND SystemIsIdle(TargetSystem) ),
    ENFORCEMENT_MODE ALLOW_ACTION,
    PRIORITY 10;

STATE_TRANSITION ActivateTargetSystem :
    SUBJECT TargetSystem,
    PRECONDITION ( TrustHolds(AgentAuthorizedForStateChange) AND SystemIsIdle(TargetSystem) ),
    POSTCONDITION ( SystemIsActive(TargetSystem) ),
    ACTION SendActivateCommand,
    REVERSION_PROTOCOL DeactivationRollback,
    GOVERNED_BY AllowTargetActivation;
```

### A.7.2 GOVERNANCE_RULE x MUTATION_RULE: Rule-of-Rule-Changes

This composition ensures that changes to the specification itself are governed. Before a MUTATION_RULE can execute, a GOVERNANCE_RULE must be satisfied.

1. `SELF_REFERENCE_POINT`: Creates a handle to the adaptable element.
2. `GOVERNANCE_RULE`: Defines the policy conditions under which self-modification is permissible (e.g., requires human-in-the-loop approval).
3. `MUTATION_RULE`: References the governance rule's ID as its APPROVAL_POLICY, creating an explicit dependency.

```omega
GOVERNANCE_RULE MutationRequiresApproval :
    SCOPE SelfModificationScope,
    PREDICATE ( IsMutationRequest(operation_type) ),
    ENFORCEMENT_MODE REQUIRE_HUMAN_APPROVAL,
    PRIORITY 100;

SELF_REFERENCE_POINT ResourceThresholdRef :
    TARGET_TYPE RESOURCE_BOUND_DEFINITION,
    ACCESS_PROTOCOL MODIFY_DEFINITION;

MUTATION_RULE GovernedThresholdAdjustment :
    TARGET_REFERENCE ResourceThresholdRef,
    CONDITION ( PerformanceMetricExceedsBaseline(current_metric) ),
    TRANSFORM_ACTION ADJUST_THRESHOLD_BY_FACTOR,
    APPROVAL_POLICY MutationRequiresApproval;
```

### A.7.3 PERCEPTION_MAP x GOVERNANCE_RULE: Observation-to-Policy Binding

This composition binds a hydrated environmental observation to a normative response. It is the standard pattern for reactive governance.

1. `ENVIRONMENT_INTERFACE_POINT`: Declares the external observation boundary.
2. `PERCEPTION_MAP`: Binds host-hydrated data into a structured internal concept.
3. `GOVERNANCE_RULE`: Uses the structured concept's properties as the PREDICATE, triggering an enforcement response.

```omega
ENVIRONMENT_INTERFACE_POINT AuditLogInput :
    SUBJECT SecurityMonitor,
    EXTERNAL_REFERENT AuditSubsystem,
    INTERACTION_TYPE ReceiveMessage,
    DATA_SCHEMA AuditEventSchema;

PERCEPTION_MAP ParseAuditEvent :
    INPUT_INTERFACE AuditLogInput,
    OUTPUT_SCHEMA StructuredAuditEventSchema,
    TRANSFORMATION_FUNCTION ParseAuditPayload;

GOVERNANCE_RULE BlockHighSeverityEvent :
    SCOPE SecurityManagement,
    PREDICATE ( IsHighSeverity(parsed_event) ),
    ENFORCEMENT_MODE PREVENT_ACTION,
    PRIORITY 95;
```

### A.7.4 Sensor-to-Action Feedback Loop

1. `ENVIRONMENT_INTERFACE_POINT`: Defines an external sensor observation boundary.
2. `PERCEPTION_MAP`: Binds host-hydrated data from the interface into a structured internal concept.
3. `STATE_TRANSITION`: Uses the structured concept as a PRECONDITION to trigger a resulting ACTION.

### A.7.5 Verifiable Learning Contract

1. `RESOURCE_BOUND`: Constrains the CPU time and memory a learning process may consume.
2. `MUTATION_RULE`: Defines how the system's knowledge base is updated based on what is learned.
3. `LEARNING_AXIOM`: Composes the above by declaring the learning task's objective while operating within the CONSTRAINT_SET and using the specified KNOWLEDGE_UPDATE_RULE.

### A.7.6 Minimal Strict End-to-End Composition

The following compact example exercises the Can/May/Do path and the mutation-learning path in one Strict-profile specification. It is intended as a grammar-composition specimen, not as a domain recommendation. Host registries supply the listed predicate functions and host actions; the Omega source binds them structurally.

```omega
PROFILE Strict;

MODULE MinimalGovernancePath

DATA_TYPE_SCHEMA StructuredAuditEventSchema :
    DEFINITION (
        VAR severity : STRING;
        VAR subject_id : STRING;
    )
    SEMANTIC_PROPERTIES { SecurityEvent };

DATA_TYPE_SCHEMA PolicyUpdateSchema :
    DEFINITION (
        VAR threshold_delta : INTEGER;
    );

ENVIRONMENT_INTERFACE_POINT AuditEventInput :
    SUBJECT SecurityMonitor,
    EXTERNAL_REFERENT AuditSubsystem,
    INTERACTION_TYPE RECEIVE_MESSAGE,
    DATA_SCHEMA StructuredAuditEventSchema;

PERCEPTION_MAP BindAuditEvent :
    INPUT_INTERFACE AuditEventInput,
    OUTPUT_SCHEMA StructuredAuditEventSchema,
    TRANSFORMATION_FUNCTION HYDRATE_AUDIT_EVENT;

GOVERNANCE_RULE AllowQuarantineForHighSeverity :
    SCOPE ApplyQuarantine,
    PREDICATE ( IsHighSeverity(structured_event) ),
    ENFORCEMENT_MODE ALLOW_ACTION,
    PRIORITY 50;

STATE_TRANSITION QuarantineSubject :
    SUBJECT MonitoredAgent,
    PRECONDITION ( IsHighSeverity(structured_event) ),
    POSTCONDITION ( IsQuarantined(MonitoredAgent) ),
    ACTION ApplyQuarantine,
    GOVERNED_BY AllowQuarantineForHighSeverity;

RESOURCE_BOUND MaxPolicyUpdateEvaluations :
    SUBJECT SecurityMonitor,
    TYPE EVALUATION_STEPS,
    METRIC STEP_COUNT,
    THRESHOLD 1000,
    VIOLATION_POLICY HALT_EVALUATION;

SELF_REFERENCE_POINT AlertThresholdRef :
    TARGET_TYPE RESOURCE_BOUND_DEFINITION,
    ACCESS_PROTOCOL MODIFY_DEFINITION;

MUTATION_RULE AdjustAlertThreshold :
    TARGET_REFERENCE AlertThresholdRef,
    CONDITION ( FalsePositiveRateExceedsLimit(SecurityMonitor) ),
    TRANSFORM_ACTION ADJUST_THRESHOLD_BY_FACTOR,
    APPROVAL_POLICY REQUIRE_HUMAN_AUTHORIZATION,
    CONSTRAINT_SET { MaxPolicyUpdateEvaluations };

LEARNING_AXIOM TuneAlertThreshold :
    INPUT_SCHEMA StructuredAuditEventSchema,
    OUTPUT_SCHEMA PolicyUpdateSchema,
    OBJECTIVE_METRIC FALSE_POSITIVE_RATE,
    CONSTRAINT_SET { MaxPolicyUpdateEvaluations },
    KNOWLEDGE_UPDATE_RULE AdjustAlertThreshold;

END MODULE;
```

---

## A.8 Reserved Words and Keywords

The following words are reserved in Omega-Code and cannot be used as identifiers.

```
ACCESS_PROTOCOL         ACCOUNTABILITY_CHAIN    ACTION                  AND
APPROVAL_POLICY         AS                      ASSIGN                  AUTHORIZED_BY
BOOLEAN                 BREAK                   CONDITION               CONSTRAINT_SET
CONTEXT_RULE            CONTINUE                DATA_SCHEMA             DATA_TYPE_SCHEMA
DECLARE                 DEFINITION              DEFINITION_SCHEMA       ELSE
END FUNCTION            END IF                  END LOOP                END MODULE
ENFORCEMENT_MODE        ENVIRONMENT_INTERFACE_POINT  EXTERNAL_REFERENT  FALSE
FIELD                   FLOAT                   FOR                     FUNCTION
GOVERNANCE_RULE         GOVERNED_BY             IF                      IN
INCOHERENCE_TOLERANCE   INPUT_INTERFACE         INPUT_SCHEMA            INTEGER
INTERACTION_TYPE        INTERVAL_A              INTERVAL_B              KNOWLEDGE_UPDATE_RULE
LEARNING_AXIOM          LOOP                    METRIC                  META_DEFINITION_RULE
MODALITY                MODULE                  MUTATION_RULE           NOT
OBJECT                  OBJECTIVE_METRIC        OR                      OUTPUT_SCHEMA
PARENT_CONTEXT          PERCEPTION_MAP          POSTCONDITION           PRECONDITION
PREDICATE               PRIORITY                PROFILE                 PROOF_PROTOCOL
PROPERTY                RESOURCE_BOUND          RETURN                  RETURNS
REVERSION_PROTOCOL      REVOCATION_PROTOCOL     ROLLBACK_CONDITION      SCOPE
SELF_REFERENCE_POINT    SEMANTIC_PROPERTIES     STATE_TRANSITION        STRING
SUBJECT                 SUBJECT_A               SUBJECT_B               TARGET_REFERENCE
TARGET_TYPE             TEMPORAL_RELATION       THEN                    THRESHOLD
TO                      TRANSFORMATION_FUNCTION TRANSFORM_ACTION        TRUE
TRUST_ELEMENT           TYPE                    UNCERTAINTY_MODEL       VALIDATION_PROTOCOL
VAR                     VIOLATION_POLICY        VOID                    WHILE
```

---

## A.9 Primitive Summary Table

| Primitive Name | Purpose | Key Parameters | Semantic Ref |
| :--- | :--- | :--- | :--- |
| `CONTEXT_RULE` | Defines a formal reasoning context. | `Modality`, `IncoherenceTolerance` | SS5.1.1 |
| `TEMPORAL_RELATION` | Asserts temporal order between entities. | `SubjectA`, `SubjectB`, `Type` | SS5.1.2 |
| `RESOURCE_BOUND` | Declares a limit on a resource. | `Subject`, `Type`, `Metric`, `Threshold` | SS5.1.3 |
| `ENVIRONMENT_INTERFACE_POINT` | Defines a system-environment boundary. | `Subject`, `ExternalReferent`, `InteractionType` | SS5.1.4 |
| `DATA_TYPE_SCHEMA` | Defines a custom structured data type. | `Definition`, `SemanticProperties` | SS5.2.1 |
| `STATE_TRANSITION` | Defines host-action authorization and postcondition verification. | `Subject`, `Precondition`, `Postcondition`, `Action`, `GovernedBy` | SS5.2.2 |
| `TRUST_ELEMENT` | Makes a verifiable claim about an entity. | `Subject`, `Predicate`, `Object`, `ProofProtocol` | SS5.2.3 |
| `GOVERNANCE_RULE` | Defines a normative policy. | `Scope`, `Predicate`, `EnforcementMode` | SS5.3.1 |
| `SELF_REFERENCE_POINT` | Creates a handle to the system's own definition. | `TargetType`, `AccessProtocol` | SS5.3.2 |
| `MUTATION_RULE` | Defines a rule for self-modification. | `TargetReference`, `Condition`, `TransformAction` | SS5.3.3 |
| `PERCEPTION_MAP` | Binds hydrated observations to internal concepts. | `InputInterface`, `OutputSchema`, `TransformationFunction` | SS5.3.4 |
| `LEARNING_AXIOM` | Defines a formal contract for a learning process. | `InputSchema`, `ObjectiveMetric`, `KnowledgeUpdateRule` | SS5.3.5 |
| `META_DEFINITION_RULE` | Defines how to extend the language's own concepts. | `TargetType`, `DefinitionSchema`, `ValidationProtocol` | SS5.3.6 |

(Semantic Ref column uses the prefix "SS" for Technical Specifications v1.4 section numbers.)

---

## A.10 Full EBNF Grammar

The grammar below is the authoritative, complete EBNF for Omega-Code. It reproduces the canonical grammar from Reference Manual Section 13 with two corrections applied (see footnotes at the end of this section).

```ebnf
(* Top-level Structure *)
OmegaCode ::= [ ProfileDeclaration ] { ModuleDefinition | Statement | Comment }

(* Profile Declaration: optional, compilation-unit level. See A.2.3. *)
ProfileDeclaration ::= 'PROFILE' ( 'Strict' | 'Extended' ) ';'

(* Module Definition *)
ModuleDefinition ::= 'MODULE' <ModuleName> <Block> 'END MODULE' [ ';' ]
ModuleName ::= <Identifier>

(* Block Structure: A sequence of statements or comments *)
Block ::= { Statement | Comment }

(* Statements can be simple or compound. Comments can appear anywhere. *)
Statement ::= SimpleStatement ';'
            | CompoundStatement
            | PrimitiveCall ';' (* Primitive calls are standalone statements *)

SimpleStatement ::= Assignment
                  | ReturnStatement
                  | FunctionCall
                  | ActionCall (* For inherent operations like LOG, INCREMENT *)
                  | VariableDeclaration (* Variable declarations require a terminating semicolon *)
                  | 'BREAK'
                  | 'CONTINUE'

CompoundStatement ::= IfStatement
                    | LoopStatement
                    | FunctionDefinition

Assignment ::= <VariableName> 'ASSIGN' <Expression>
ReturnStatement ::= 'RETURN' [ <Expression> ]

(* Control Flow *)
IfStatement ::= 'IF' <BooleanExpression> 'THEN' <Block> [ 'ELSE' <Block> ] 'END IF' [ ';' ]
LoopStatement ::= 'LOOP' ( 'WHILE' <BooleanExpression> | 'FOR' <VariableName> 'IN' <Range> ) <Block> 'END LOOP' [ ';' ]
Range ::= <Expression> 'TO' <Expression> | <Identifier> (* e.g., '1 TO 10', 'list_of_items' *)

(* Function Definition *)
FunctionDefinition ::= 'FUNCTION' <FunctionName> '(' [ <ParameterList> ] ')' [ 'RETURNS' <ReturnType> ] <Block> 'END FUNCTION' [ ';' ]
FunctionName ::= <Identifier>
ParameterList ::= <Parameter> { ',' <Parameter> }
Parameter ::= <ParameterName> ':' <DataType>
ParameterName ::= <Identifier>
ReturnType ::= <DataType> | 'VOID'

(* Variable Declaration *)
VariableDeclaration ::= ( 'DECLARE' | 'VAR' ) <VariableName> [ ':' <DataType> ] [ 'AS' <InitialValue> ]
VariableName ::= <Identifier>
InitialValue ::= <Expression>

(* Primitive Data Types and Expressions *)
DataType ::= 'BOOLEAN' | 'INTEGER' | 'FLOAT' | 'STRING' | <SchemaID> | <Identifier> (* for user-defined types *)
Expression ::= <Literal> | <VariableName> | <FunctionCall> | <OperatorExpression>
Literal ::= 'TRUE' | 'FALSE' | <IntegerLiteral> | <FloatLiteral> | <StringLiteral>
IntegerLiteral ::= <Digit> { <Digit> }
FloatLiteral ::= <IntegerLiteral> '.' <IntegerLiteral>
StringLiteral ::= '"' { <CharInString> } '"' (* Changed to CharInString *)
Char ::= (* any Unicode character *)
Digit ::= '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9'
Letter ::= 'a' | ... | 'z' | 'A' | ... | 'Z'
Identifier ::= <Letter> { <Letter> | <Digit> | '_' }

OperatorExpression ::= <Operand> <Operator> <Operand> | <UnaryOperator> <Operand>
Operand ::= <Expression> | '(' <Expression> ')'
Operator ::= '+' | '-' | '*' | '/' | '==' | '!=' | '<' | '>' | '<=' | '>=' | 'AND' | 'OR' | 'NOT'
UnaryOperator ::= 'NOT' | '-'

FunctionCall ::= <FunctionName> '(' [ <ArgumentList> ] ')'
ArgumentList ::= <Expression> { ',' <Expression> }

ActionCall ::= <ActionID> '(' [ <ArgumentList> ] ')' (* For inherent operations like LOG, INCREMENT *)

(* Boolean Expressions (for Conditions and Predicates). Precedence: NOT > AND > OR. *)
BooleanExpression ::= <OrExpression>
OrExpression ::= <AndExpression> { 'OR' <AndExpression> }
AndExpression ::= <NotExpression> { 'AND' <NotExpression> }
NotExpression ::= [ 'NOT' ] <PrimaryBoolean>
PrimaryBoolean ::= 'TRUE'
                 | 'FALSE'
                 | '(' <BooleanExpression> ')'
                 | <ComparisonExpression>
                 | <MembershipExpression>
                 | <FunctionCall> (* only if registered as returning BOOLEAN in this slot *)
ComparisonExpression ::= <Expression> ( '==' | '!=' | '<' | '>' | '<=' | '>=' ) <Expression>
MembershipExpression ::= <Expression> 'IN' <SetExpression>
SetExpression ::= '{' <Expression> { ',' <Expression> } '}'

(* Numeric Expressions (for Quantities and Priorities) *)
NumericExpression ::= <IntegerLiteral> | <FloatLiteral>
                    | <VariableName> (* resolves to numeric type *)
                    | '(' <NumericExpression> ')'
                    | <NumericExpression> <ArithmeticOperator> <NumericExpression>
                    | <UnaryNumericOperator> <NumericExpression>
ArithmeticOperator ::= '+' | '-' | '*' | '/'
UnaryNumericOperator ::= '-'

(* Characters for specific contexts *)
CharInString ::= (* any Unicode character except '"' *)
CharInComment ::= (* any Unicode character except newline, or '*' followed by ')' for BlockComment *)

(* Comments *)
Comment ::= BlockComment | LineComment
BlockComment ::= '(*' { <CharInComment> } '*)'
LineComment ::= '--' { <CharInComment> } <Newline>
Newline ::= '\n' | '\r\n' | '\r'

(* Identifiers for Primitives and Entities *)
ContextID ::= <Identifier>
EntityID ::= <Identifier>
TemporalRelationTypeID ::= <Identifier>
IntervalDefinitionID ::= <Identifier>
BoundID ::= <Identifier>
ResourceTypeID ::= <Identifier>
MetricID ::= <Identifier>
PolicyID ::= <Identifier>
InterfaceID ::= <Identifier>
InteractionTypeID ::= <Identifier>
SchemaID ::= <Identifier>
ActionID ::= <Identifier> (* Named inherent language operation *)
ProtocolID ::= <Identifier>
RuleID ::= <Identifier>
MutationRuleID ::= <RuleID>
ScopeID ::= <Identifier>
EnforcementModeID ::= <Identifier>
Value ::= <NumericExpression> (* for Priority and other simple values where numeric is expected *)
PointID ::= <Identifier>
TargetTypeID ::= <Identifier>
SelfReferencePointID ::= <Identifier>
TransformAction ::= <ActionID> (* Refers to a named action for mutation *)
ModelID ::= <Identifier> (* for UncertaintyModel *)
PropertyID ::= <Identifier>
TransitionID ::= <Identifier>
ElementID ::= <Identifier>
MapID ::= <Identifier>
AxiomID ::= <Identifier>
RelationID ::= <Identifier>
ResourceBoundID ::= <Identifier>
ChainID ::= <Identifier>
BoundIDList ::= '{' <ResourceBoundID> { ',' <ResourceBoundID> } '}'

(* Revised Schema Definition: defines fields within a data type schema *)
SchemaDefinition ::= '(' { FieldDefinition } ')'
FieldDefinition ::= ( 'VAR' | 'FIELD' | 'PROPERTY' ) <FieldName> ':' <DataType> [ 'AS' <InitialValue> ] ';'
FieldName ::= <Identifier>
Quantity ::= <NumericExpression> (* for Threshold *)


(* Primitive Calls - Detailed in Section A.6 *)
PrimitiveCall ::= ContextRuleCall
                | TemporalRelationCall
                | ResourceBoundCall
                | EnvironmentInterfacePointCall
                | DataTypeSchemaCall
                | StateTransitionCall
                | TrustElementCall
                | GovernanceRuleCall
                | SelfReferencePointCall
                | MutationRuleCall
                | PerceptionMapCall
                | LearningAxiomCall
                | MetaDefinitionRuleCall


ContextRuleCall ::= 'CONTEXT_RULE' <ContextID> ':' 'MODALITY' '{' <ModalityType> { ',' <ModalityType> } '}' [ ',' 'INCOHERENCE_TOLERANCE' <Expression> ] [ ',' 'PARENT_CONTEXT' <ContextID> ]
ModalityType ::= <Identifier>

TemporalRelationCall ::= 'TEMPORAL_RELATION' <RelationID> ':' 'SUBJECT_A' <EntityID> ',' 'SUBJECT_B' <EntityID> ',' 'TYPE' <TemporalRelationTypeID> [ ',' 'INTERVAL_A' <IntervalDefinitionID> ] [ ',' 'INTERVAL_B' <IntervalDefinitionID> ]

ResourceBoundCall ::= 'RESOURCE_BOUND' <BoundID> ':' 'SUBJECT' <EntityID> ',' 'TYPE' <ResourceTypeID> ',' 'METRIC' <MetricID> ',' 'THRESHOLD' <NumericExpression> ',' 'VIOLATION_POLICY' <PolicyID>

EnvironmentInterfacePointCall ::= 'ENVIRONMENT_INTERFACE_POINT' <InterfaceID> ':' 'SUBJECT' <EntityID> ',' 'EXTERNAL_REFERENT' <EntityID> ',' 'INTERACTION_TYPE' <InteractionTypeID> ',' 'DATA_SCHEMA' <SchemaID> [ ',' 'UNCERTAINTY_MODEL' <ModelID> ]

DataTypeSchemaCall ::= 'DATA_TYPE_SCHEMA' <SchemaID> ':' 'DEFINITION' <SchemaDefinition> [ 'SEMANTIC_PROPERTIES' '{' <PropertyID> { ',' <PropertyID> } '}' ]

StateTransitionCall ::= 'STATE_TRANSITION' <TransitionID> ':' 'SUBJECT' <EntityID> ',' 'PRECONDITION' <BooleanExpression> ',' 'POSTCONDITION' <BooleanExpression> ',' 'ACTION' <ActionID> [ ',' 'REVERSION_PROTOCOL' <ProtocolID> ] [ ',' 'AUTHORIZED_BY' <ElementID> ] ',' 'GOVERNED_BY' <RuleID> [ ',' 'CONSTRAINT_SET' <BoundIDList> ]

TrustElementCall ::= 'TRUST_ELEMENT' <ElementID> ':' 'SUBJECT' <EntityID> ',' 'PREDICATE' <BooleanExpression> ',' 'OBJECT' <EntityID> [ ',' 'PROOF_PROTOCOL' <ProtocolID> ] [ ',' 'REVOCATION_PROTOCOL' <ProtocolID> ] [ ',' 'ACCOUNTABILITY_CHAIN' <ChainID> ]

GovernanceRuleCall ::= 'GOVERNANCE_RULE' <RuleID> ':' 'SCOPE' <ScopeID> ',' 'PREDICATE' <BooleanExpression> ',' 'ENFORCEMENT_MODE' <EnforcementModeID> [ ',' 'PRIORITY' <NumericExpression> ] [ ',' 'CONSTRAINT_SET' <BoundIDList> ]

SelfReferencePointCall ::= 'SELF_REFERENCE_POINT' <PointID> ':' 'TARGET_TYPE' <TargetTypeID> ',' 'ACCESS_PROTOCOL' <ProtocolID>

MutationRuleCall ::= 'MUTATION_RULE' <RuleID> ':' 'TARGET_REFERENCE' <SelfReferencePointID> ',' 'CONDITION' <BooleanExpression> ',' 'TRANSFORM_ACTION' <ActionID> [ ',' 'APPROVAL_POLICY' <PolicyID> ] [ ',' 'CONSTRAINT_SET' <BoundIDList> ]

PerceptionMapCall ::= 'PERCEPTION_MAP' <MapID> ':' 'INPUT_INTERFACE' <InterfaceID> ',' 'OUTPUT_SCHEMA' <SchemaID> ',' 'TRANSFORMATION_FUNCTION' <ActionID> [ ',' 'UNCERTAINTY_MODEL' <ModelID> ]

LearningAxiomCall ::= 'LEARNING_AXIOM' <AxiomID> ':' 'INPUT_SCHEMA' <SchemaID> ',' 'OUTPUT_SCHEMA' <SchemaID> ',' 'OBJECTIVE_METRIC' <MetricID> ',' 'CONSTRAINT_SET' <BoundIDList> ',' 'KNOWLEDGE_UPDATE_RULE' <MutationRuleID> [ ',' 'ROLLBACK_CONDITION' <BooleanExpression> ]

MetaDefinitionRuleCall ::= 'META_DEFINITION_RULE' <RuleID> ':' 'TARGET_TYPE' <TargetTypeID> ',' 'DEFINITION_SCHEMA' <SchemaDefinition> ',' 'VALIDATION_PROTOCOL' <ProtocolID>
```

**Footnote (Defect 1, META_DEFINITION_RULE field type and related schema-ID inconsistencies):** Note: Earlier versions of the Reference Manual contained a typo in Section 8 listing META_DEFINITION_RULE's DEFINITION_SCHEMA field as `<DataSchemaID>`. The correct type is `<SchemaDefinition>`, an inline schema literal. The same RM Section 8 inconsistency uses `<DataSchemaID>` for PERCEPTION_MAP's OUTPUT_SCHEMA and for LEARNING_AXIOM's INPUT_SCHEMA and OUTPUT_SCHEMA. This appendix adopts `<SchemaID>` (a reference to a named schema) in all three of those cases, consistent with RM Section 13's full EBNF and with Tech-Spec Section 2.2.

**Footnote (Defect 2, VariableDeclaration classification):** Note: Earlier versions of the Reference Manual classified VariableDeclaration as a CompoundStatement, which contradicted the documented requirement that variable declarations terminate with a semicolon. This appendix corrects the classification.

---

## A.11 Extensibility via META_DEFINITION_RULE

The META_DEFINITION_RULE primitive is the mechanism by which Omega-Code remains future-proof. Rather than hardcoding all possible values for sanctioned extensible categories such as ResourceTypeID, ModalityType, InteractionTypeID, MetricID, or PropertyID, the language provides a formal mechanism for creating new ones. TargetTypeID and the formal self-reference target categories are Constitutional and are not extensible by META_DEFINITION_RULE. This allows the language to adapt to unforeseen requirements without altering the core grammar or parser.

**Function:** META_DEFINITION_RULE defines a rule for creating new instances of a sanctioned extensible TARGET_TYPE category. The DEFINITION_SCHEMA specifies the structure (as an inline SchemaDefinition) that a new definition must conform to. The VALIDATION_PROTOCOL ensures that any new definition is well-formed and compliant before it is accepted by the processing system. A META_DEFINITION_RULE whose TARGET_TYPE is TARGET_TYPE_ID or another Constitutional category is rejected at load time.

**Usage pattern:** Declare a META_DEFINITION_RULE once per new type category. Subsequently, use the new type identifier wherever the corresponding extensible category appears in a primitive call. The processing system validates new instances against the DEFINITION_SCHEMA at specification-load time.

```ebnf
MetaDefinitionRuleCall ::= 'META_DEFINITION_RULE' <RuleID> ':' 'TARGET_TYPE' <TargetTypeID> ',' 'DEFINITION_SCHEMA' <SchemaDefinition> ',' 'VALIDATION_PROTOCOL' <ProtocolID>
```

Example: defining a new resource type category and then using it.

```omega
META_DEFINITION_RULE DefineNewResourceType :
    TARGET_TYPE RESOURCE_TYPE_ID,
    DEFINITION_SCHEMA (
        VAR name : STRING;
        VAR measurementUnit : STRING;
        VAR accuracyTolerance : FLOAT;
    ),
    VALIDATION_PROTOCOL SchemaValidation;

-- Once validated, the new resource type identifier may be used where ResourceTypeID is admitted:
RESOURCE_BOUND MaxGpuSeconds :
    SUBJECT InferenceWorker,
    TYPE GpuSecond,
    METRIC Seconds,
    THRESHOLD 30,
    VIOLATION_POLICY HaltEvaluation;
```

---

## A.12 Parser Validation Test Suite

The following snippets constitute the normative parser test suite for Omega-Code. Implementations must accept all Valid snippets and reject all Invalid snippets with the reasons stated.

### A.12.1 Valid Test Snippets

These snippets must be successfully parsed.

**Snippet 1: Minimal Module Definition**
```omega
MODULE EmptyModule
    -- This is an empty module block
END MODULE;
```

**Snippet 2: Full Primitive Call with Optional Fields**
```omega
TEMPORAL_RELATION FullRelationExample:
    SUBJECT_A Event_A,
    SUBJECT_B Event_B,
    TYPE OVERLAPS,
    INTERVAL_A Interval_One,
    INTERVAL_B Interval_Two;
```

**Snippet 3: Nested Control Flow**
```omega
LOOP FOR i IN 1 TO 5
    IF i > 2 THEN
        BREAK;
    ELSE
        CONTINUE;
    END IF;
END LOOP;
```

### A.12.2 Invalid (Negative) Test Snippets

These snippets must be rejected by the parser.

**Snippet 1: Missing Semicolon**
```omega
VAR x: INTEGER AS 5 --<-- Missing semicolon
VAR y: INTEGER AS 10;
```
*Reason for Invalidity:* The `VariableDeclaration` is a `SimpleStatement` and requires a terminating semicolon (`;`).

**Snippet 2: Incorrect Keyword Order in Primitive**
```omega
RESOURCE_BOUND BadOrder:
    SUBJECT MyProcess,
    THRESHOLD 512,  --<-- THRESHOLD appears before TYPE and METRIC
    TYPE Memory,
    METRIC Megabytes,
    VIOLATION_POLICY Halt;
```
*Reason for Invalidity:* The `ResourceBoundCall` rule specifies a strict order for its parameters (`SUBJECT`, `TYPE`, `METRIC`, `THRESHOLD`, `VIOLATION_POLICY`).

**Snippet 3: Unmatched Block Terminator**
```omega
IF TRUE THEN
    VAR a: BOOLEAN AS FALSE;
END LOOP; --<-- Incorrect terminator. Should be END IF.
```
*Reason for Invalidity:* An `IfStatement` must be terminated with `END IF`, not `END LOOP`.

**Snippet 4: Using Reserved Keyword as an Identifier**
```omega
VAR MODULE: STRING AS "MyData"; --<-- 'MODULE' is a reserved keyword.
```
*Reason for Invalidity:* `MODULE` is a reserved keyword and cannot be used as a `<VariableName>` identifier.

**Snippet 5: STATE_TRANSITION Missing GOVERNED_BY**
```omega
STATE_TRANSITION UnsafeTransition :
    SUBJECT TargetSystem,
    PRECONDITION TRUE,
    POSTCONDITION TRUE,
    ACTION SendActivateCommand;
```
*Reason for Invalidity:* `StateTransitionCall` requires `GOVERNED_BY <RuleID>`. A transition without a governing rule is malformed.

---

## A.13 Conformance and References

This grammar specification defines the canonical Omega-Code tokenization, keyword set, and EBNF productions. For full conformance and correct evaluator behavior:

- See 03-OMEGA-01_LANGUAGE_SPEC.md for the conceptual model, primitive roles, and integration with SGF/HFF/AFP.  
- See 03-OMEGA-03_IMPLEMENTERS_GUIDE.md for required static and runtime checks, profile enforcement, determinism, and safety-kernel behavior.  
- See 03-OMEGA-04_EXTENSION_GOVERNANCE.md for rules governing extensions to the Omega vocabulary, profiles, and composition patterns.  
- See `support/03-OMEGA_WORKED_EXAMPLES.md` as a non-normative but recommended test corpus for parser and evaluator validation.

A parser or evaluator is considered grammatically conformant when it:

- Accepts all positive example snippets and complete modules defined for this grammar.  
- Rejects all negative snippets documented in the test corpus with the specified error conditions.  
- Treats the Strict and Extended profiles according to the productions and annotations in this specification.
