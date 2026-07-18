import { Document, Chunk, FailureAnalysis, EvalMetric, PresetQA } from './types';

export const INITIAL_DOCUMENTS: Document[] = [
  {
    id: 'doc-1',
    name: 'Climate_Action_Plan_2026.pdf',
    type: 'pdf',
    domain: 'Climate Science',
    pages: 24,
    chunksCount: 120,
    uploadDate: '2026-04-12',
    status: 'indexed',
    fileSize: '4.2 MB',
    author: 'Municipal Sustainability Office',
    description: 'Framework outlining carbon reduction goals, municipal transit electrification, and green urban planning initiatives for the upcoming fiscal cycle.',
    extractedTextPreview: 'SECTION 3.2: EMISSION REDUCTION SCHEDULES. The city targets a 45% reduction in carbon emissions relative to the 2018 baseline by December 2030. Key milestones include complete electrification of the public transit bus fleet (currently at 35% electrification) and mandatory solar roofing retrofits for commercial properties exceeding 15,000 sq ft. Finance allocation for this transition is secured via green municipal bonds.'
  },
  {
    id: 'doc-2',
    name: 'M_and_A_Agreement_Draft.docx',
    type: 'docx',
    domain: 'Legal Compliance',
    pages: 8,
    chunksCount: 42,
    uploadDate: '2026-06-02',
    status: 'indexed',
    fileSize: '1.8 MB',
    author: 'Sterling & Co. Legal Partners',
    description: 'Confidential draft detailing acquisition terms, representation clauses, indemnification caps, and pre-closing covenants between Apex Enterprises and Core Systems.',
    extractedTextPreview: 'ARTICLE IX: INDEMNIFICATION AND LIABILITIES. Section 9.1: Indemnification Cap. Except in cases of fraud or intentional misrepresentation, the maximum aggregate liability of the Selling Parties for any losses, claims, or damages arising out of breaches of representations and warranties shall not exceed $15,000,000 (the "Indemnification Cap"). Any individual claim must exceed $50,000 to be eligible for indemnification.'
  },
  {
    id: 'doc-3',
    name: 'Q2_Financial_Report.pdf',
    type: 'pdf',
    domain: 'Finance',
    pages: 18,
    chunksCount: 74,
    uploadDate: '2026-07-10',
    status: 'indexed',
    fileSize: '2.9 MB',
    author: 'Atlas Global Corporate Finance',
    description: 'Consolidated balance sheets, cashflow visualizations, operating margins, and EBITDA performance analysis for Q2 FY2026.',
    extractedTextPreview: 'FINANCIAL HIGHLIGHTS - Q2 FY2026. Gross revenue reached $48.2M, representing a 14% year-over-year increase. Net operating income stood at $12.4M, driven by a 22% reduction in cloud server overhead through container optimization. Cash reserves remained strong at $84.5M, supporting planned expansion into EMEA regions.'
  },
  {
    id: 'doc-4',
    name: 'EHR_Standardization_Guide.txt',
    type: 'txt',
    domain: 'Healthcare Informatics',
    pages: 6,
    chunksCount: 28,
    uploadDate: '2026-07-15',
    status: 'indexed',
    fileSize: '450 KB',
    author: 'Health IT Advisory Committee',
    description: 'Technical reference manual outlining Electronic Health Record interoperability standards, metadata schemas, and FHIR API security credentials.',
    extractedTextPreview: 'STANDARD PROTOCOL 4.01: METADATA SEGREGATION. To comply with patient confidentiality mandates, electronic health records (EHR) must implement strict structural separation of patient identifiers and clinical records. Metadata schemas must utilize FHIR (Fast Healthcare Interoperability Resources) v4 JSON objects. The metadata packet must contain validated tenant keys, with transmission secured via OAuth 2.0 with mutual TLS.'
  }
];

export const MOCK_CHUNKS: Record<string, Chunk[]> = {
  'doc-1': [
    {
      id: 'chunk-1-1',
      documentId: 'doc-1',
      documentName: 'Climate_Action_Plan_2026.pdf',
      chunkNumber: 1,
      pageNumber: 1,
      text: 'Executive Summary: Atlas Municipalities seek to build climate resilience by addressing the three primary emissions sources: transportation (42%), residential energy (28%), and waste management (14%). Strategic goals aim for net-zero by 2050.',
      status: 'indexed',
      tokenCount: 142
    },
    {
      id: 'chunk-1-2',
      documentId: 'doc-1',
      documentName: 'Climate_Action_Plan_2026.pdf',
      chunkNumber: 2,
      pageNumber: 3,
      text: 'SECTION 3.2: EMISSION REDUCTION SCHEDULES. The city targets a 45% reduction in carbon emissions relative to the 2018 baseline by December 2030. Key milestones include complete electrification of the public transit bus fleet (currently at 35% electrification).',
      status: 'indexed',
      tokenCount: 168
    },
    {
      id: 'chunk-1-3',
      documentId: 'doc-1',
      documentName: 'Climate_Action_Plan_2026.pdf',
      chunkNumber: 3,
      pageNumber: 4,
      text: 'To accelerate building decarbonization, Atlas city mandates solar roofing retrofits for all commercial properties exceeding 15,000 sq ft. Finance allocation for this transition is secured via green municipal bonds with special local tax benefits.',
      status: 'indexed',
      tokenCount: 152
    }
  ],
  'doc-2': [
    {
      id: 'chunk-2-1',
      documentId: 'doc-2',
      documentName: 'M_and_A_Agreement_Draft.docx',
      chunkNumber: 1,
      pageNumber: 1,
      text: 'This MERGER AND ACQUISITION AGREEMENT is entered into on June 2, 2026, by and between Apex Enterprises ("Buyer") and Core Systems Corp ("Seller"). It defines the purchase price of $120,000,000 and all subsequent closing requirements.',
      status: 'indexed',
      tokenCount: 180
    },
    {
      id: 'chunk-2-2',
      documentId: 'doc-2',
      documentName: 'M_and_A_Agreement_Draft.docx',
      chunkNumber: 2,
      pageNumber: 5,
      text: 'ARTICLE IX: INDEMNIFICATION AND LIABILITIES. Section 9.1: Indemnification Cap. Except in cases of fraud or intentional misrepresentation, the maximum aggregate liability of the Selling Parties for any losses or claims arising out of breaches shall not exceed $15,000,000.',
      status: 'indexed',
      tokenCount: 195
    },
    {
      id: 'chunk-2-3',
      documentId: 'doc-2',
      documentName: 'M_and_A_Agreement_Draft.docx',
      chunkNumber: 3,
      pageNumber: 6,
      text: 'Section 9.2: Claim Thresholds. Any individual claim must exceed $50,000 to be eligible for indemnification, preventing petty disputes. A basket of $500,000 must accumulate before any actual payment liability triggers.',
      status: 'indexed',
      tokenCount: 160
    }
  ],
  'doc-3': [
    {
      id: 'chunk-3-1',
      documentId: 'doc-3',
      documentName: 'Q2_Financial_Report.pdf',
      chunkNumber: 1,
      pageNumber: 2,
      text: 'FINANCIAL HIGHLIGHTS - Q2 FY2026. Gross revenue reached $48.2M, representing a 14% year-over-year increase. This growth is predominantly driven by our SaaS product division expanding in the North American market.',
      status: 'indexed',
      tokenCount: 145
    },
    {
      id: 'chunk-3-2',
      documentId: 'doc-3',
      documentName: 'Q2_Financial_Report.pdf',
      chunkNumber: 2,
      pageNumber: 5,
      text: 'Net operating income stood at $12.4M, driven by a 22% reduction in cloud server overhead through container optimization. Cash reserves remained strong at $84.5M, supporting planned expansion into EMEA regions.',
      status: 'indexed',
      tokenCount: 155
    },
    {
      id: 'chunk-3-3',
      documentId: 'doc-3',
      documentName: 'Q2_Financial_Report.pdf',
      chunkNumber: 3,
      pageNumber: 12,
      text: 'CAPITAL EXPENDITURES (CapEx). Capital outlay for Q2 was $4.1M, primarily allocated to data center server clusters and GPU acquisition for local model orchestration. Operational expenses (OpEx) decreased by 4.5% overall.',
      status: 'indexed',
      tokenCount: 162
    }
  ],
  'doc-4': [
    {
      id: 'chunk-4-1',
      documentId: 'doc-4',
      documentName: 'EHR_Standardization_Guide.txt',
      chunkNumber: 1,
      pageNumber: 1,
      text: 'STANDARD PROTOCOL 4.01: METADATA SEGREGATION. To comply with patient confidentiality mandates, electronic health records (EHR) must implement strict structural separation of patient identifiers and clinical records.',
      status: 'indexed',
      tokenCount: 130
    },
    {
      id: 'chunk-4-2',
      documentId: 'doc-4',
      documentName: 'EHR_Standardization_Guide.txt',
      chunkNumber: 2,
      pageNumber: 2,
      text: 'Metadata schemas must utilize FHIR (Fast Healthcare Interoperability Resources) v4 JSON objects. The metadata packet must contain validated tenant keys, with transmission secured via OAuth 2.0 with mutual TLS authorization.',
      status: 'indexed',
      tokenCount: 175
    }
  ]
};

export const PRESET_QAS: PresetQA[] = [
  {
    question: 'What are our targets for carbon neutrality by 2030?',
    answer: 'According to the municipal sustainability targets outlined in the **Climate Action Plan 2026**, the city targets a **45% reduction in carbon emissions** relative to the 2018 baseline by December 2030 [Climate_Action_Plan_2026.pdf, p. 3]. The plan details specific action items including transitioning the public transit bus fleet to full electrification (currently at 35%) [Climate_Action_Plan_2026.pdf, p. 3] and imposing mandatory solar roofing retrofits for commercial properties larger than 15,000 sq ft [Climate_Action_Plan_2026.pdf, p. 4].',
    citations: [
      { documentName: 'Climate_Action_Plan_2026.pdf', page: 3, chunkIndex: 2 },
      { documentName: 'Climate_Action_Plan_2026.pdf', page: 4, chunkIndex: 3 }
    ],
    retrievedChunks: [
      {
        id: 'chunk-1-2',
        documentId: 'doc-1',
        documentName: 'Climate_Action_Plan_2026.pdf',
        chunkNumber: 2,
        pageNumber: 3,
        text: 'SECTION 3.2: EMISSION REDUCTION SCHEDULES. The city targets a 45% reduction in carbon emissions relative to the 2018 baseline by December 2030. Key milestones include complete electrification of the public transit bus fleet (currently at 35% electrification).',
        status: 'indexed',
        similarityScore: 0.942,
        tokenCount: 168
      },
      {
        id: 'chunk-1-3',
        documentId: 'doc-1',
        documentName: 'Climate_Action_Plan_2026.pdf',
        chunkNumber: 3,
        pageNumber: 4,
        text: 'To accelerate building decarbonization, Atlas city mandates solar roofing retrofits for all commercial properties exceeding 15,000 sq ft. Finance allocation for this transition is secured via green municipal bonds with special local tax benefits.',
        status: 'indexed',
        similarityScore: 0.885,
        tokenCount: 152
      },
      {
        id: 'chunk-1-1',
        documentId: 'doc-1',
        documentName: 'Climate_Action_Plan_2026.pdf',
        chunkNumber: 1,
        pageNumber: 1,
        text: 'Executive Summary: Atlas Municipalities seek to build climate resilience by addressing the three primary emissions sources: transportation (42%), residential energy (28%), and waste management (14%). Strategic goals aim for net-zero by 2050.',
        status: 'indexed',
        similarityScore: 0.741,
        tokenCount: 142
      }
    ]
  },
  {
    question: 'What is the indemnification cap specified in the merger draft?',
    answer: 'As negotiated in the confidential draft of the **Merger and Acquisition Agreement**, the maximum aggregate liability of the Selling Parties for losses and breaches is capped at **$15,000,000** (known as the "Indemnification Cap") [M_and_A_Agreement_Draft.docx, p. 5]. There are two key exemptions and conditions: first, this cap does not apply in cases of fraud or intentional misrepresentation [M_and_A_Agreement_Draft.docx, p. 5]; second, any individual claim must exceed **$50,000** to be eligible for indemnification, with a baseline basket of $500,000 required before payment triggers [M_and_A_Agreement_Draft.docx, p. 6].',
    citations: [
      { documentName: 'M_and_A_Agreement_Draft.docx', page: 5, chunkIndex: 2 },
      { documentName: 'M_and_A_Agreement_Draft.docx', page: 6, chunkIndex: 3 }
    ],
    retrievedChunks: [
      {
        id: 'chunk-2-2',
        documentId: 'doc-2',
        documentName: 'M_and_A_Agreement_Draft.docx',
        chunkNumber: 2,
        pageNumber: 5,
        text: 'ARTICLE IX: INDEMNIFICATION AND LIABILITIES. Section 9.1: Indemnification Cap. Except in cases of fraud or intentional misrepresentation, the maximum aggregate liability of the Selling Parties for any losses or claims arising out of breaches shall not exceed $15,000,000.',
        status: 'indexed',
        similarityScore: 0.965,
        tokenCount: 195
      },
      {
        id: 'chunk-2-3',
        documentId: 'doc-2',
        documentName: 'M_and_A_Agreement_Draft.docx',
        chunkNumber: 3,
        pageNumber: 6,
        text: 'Section 9.2: Claim Thresholds. Any individual claim must exceed $50,000 to be eligible for indemnification, preventing petty disputes. A basket of $500,000 must accumulate before any actual payment liability triggers.',
        status: 'indexed',
        similarityScore: 0.912,
        tokenCount: 160
      },
      {
        id: 'chunk-2-1',
        documentId: 'doc-2',
        documentName: 'M_and_A_Agreement_Draft.docx',
        chunkNumber: 1,
        pageNumber: 1,
        text: 'This MERGER AND ACQUISITION AGREEMENT is entered into on June 2, 2026, by and between Apex Enterprises ("Buyer") and Core Systems Corp ("Seller"). It defines the purchase price of $120,000,000 and all subsequent closing requirements.',
        status: 'indexed',
        similarityScore: 0.692,
        tokenCount: 180
      }
    ]
  },
  {
    question: 'How does the net operating income for Q2 compare to our cloud overhead targets?',
    answer: 'In **Q2 FY2026**, Net Operating Income grew to **$12.4M** out of $48.2M gross revenue (a 14% YoY gross revenue increase) [Q2_Financial_Report.pdf, p. 2]. This operating efficiency was heavily supported by a **22% reduction in cloud server overhead** accomplished specifically through server container optimization [Q2_Financial_Report.pdf, p. 5]. Capital expenditure for the quarter was $4.1M, primarily focused on server clusters and local model GPU acquisition [Q2_Financial_Report.pdf, p. 12].',
    citations: [
      { documentName: 'Q2_Financial_Report.pdf', page: 2, chunkIndex: 1 },
      { documentName: 'Q2_Financial_Report.pdf', page: 5, chunkIndex: 2 }
    ],
    retrievedChunks: [
      {
        id: 'chunk-3-2',
        documentId: 'doc-3',
        documentName: 'Q2_Financial_Report.pdf',
        chunkNumber: 2,
        pageNumber: 5,
        text: 'Net operating income stood at $12.4M, driven by a 22% reduction in cloud server overhead through container optimization. Cash reserves remained strong at $84.5M, supporting planned expansion into EMEA regions.',
        status: 'indexed',
        similarityScore: 0.925,
        tokenCount: 155
      },
      {
        id: 'chunk-3-1',
        documentId: 'doc-3',
        documentName: 'Q2_Financial_Report.pdf',
        chunkNumber: 1,
        pageNumber: 2,
        text: 'FINANCIAL HIGHLIGHTS - Q2 FY2026. Gross revenue reached $48.2M, representing a 14% year-over-year increase. This growth is predominantly driven by our SaaS product division expanding in the North American market.',
        status: 'indexed',
        similarityScore: 0.841,
        tokenCount: 145
      },
      {
        id: 'chunk-3-3',
        documentId: 'doc-3',
        documentName: 'Q2_Financial_Report.pdf',
        chunkNumber: 3,
        pageNumber: 12,
        text: 'CAPITAL EXPENDITURES (CapEx). Capital outlay for Q2 was $4.1M, primarily allocated to data center server clusters and GPU acquisition for local model orchestration. Operational expenses (OpEx) decreased by 4.5% overall.',
        status: 'indexed',
        similarityScore: 0.798,
        tokenCount: 162
      }
    ]
  },
  {
    question: 'What are the core requirements for EHR metadata compliance?',
    answer: 'The **EHR Standardization Guide** mandates standard segregation of patient information under Standard Protocol 4.01 [EHR_Standardization_Guide.txt, p. 1]. Specifically, electronic health records (EHR) must perform a complete structural separation of patient identities from clinical data records. For compliance, metadata schemas must utilize **FHIR (Fast Healthcare Interoperability Resources) v4 JSON objects** [EHR_Standardization_Guide.txt, p. 2]. Transmissions must contain verified tenant keys and are strictly secured via **OAuth 2.0 with mutual TLS** [EHR_Standardization_Guide.txt, p. 2].',
    citations: [
      { documentName: 'EHR_Standardization_Guide.txt', page: 1, chunkIndex: 1 },
      { documentName: 'EHR_Standardization_Guide.txt', page: 2, chunkIndex: 2 }
    ],
    retrievedChunks: [
      {
        id: 'chunk-4-1',
        documentId: 'doc-4',
        documentName: 'EHR_Standardization_Guide.txt',
        chunkNumber: 1,
        pageNumber: 1,
        text: 'STANDARD PROTOCOL 4.01: METADATA SEGREGATION. To comply with patient confidentiality mandates, electronic health records (EHR) must implement strict structural separation of patient identifiers and clinical records.',
        status: 'indexed',
        similarityScore: 0.958,
        tokenCount: 130
      },
      {
        id: 'chunk-4-2',
        documentId: 'doc-4',
        documentName: 'EHR_Standardization_Guide.txt',
        chunkNumber: 2,
        pageNumber: 2,
        text: 'Metadata schemas must utilize FHIR (Fast Healthcare Interoperability Resources) v4 JSON objects. The metadata packet must contain validated tenant keys, with transmission secured via OAuth 2.0 with mutual TLS authorization.',
        status: 'indexed',
        similarityScore: 0.914,
        tokenCount: 175
      }
    ]
  }
];

export const INITIAL_METRICS: EvalMetric[] = [
  {
    name: 'Recall@5',
    value: '94.8%',
    change: '+1.4%',
    changeType: 'increase',
    description: 'Proportion of relevant chunks retrieved in the top 5 candidates across testing datasets.'
  },
  {
    name: 'MRR (Mean Reciprocal Rank)',
    value: '0.884',
    change: '+0.032',
    changeType: 'increase',
    description: 'Average reciprocal rank of the first relevant chunk. Measures retrieval ranking quality.'
  },
  {
    name: 'Answer Correctness',
    value: '89.2%',
    change: '+2.1%',
    changeType: 'increase',
    description: 'Semantic similarity and truthfulness score compared to validated ground-truth answers.'
  },
  {
    name: 'Groundedness Score',
    value: '96.5%',
    change: '+0.8%',
    changeType: 'increase',
    description: 'Percentage of claims in generated answers directly backed by retrieved context chunks (no hallucinations).'
  }
];

export const DOMAIN_PERFORMANCE = [
  { domain: 'Climate Science', recall: 96, correctness: 92, groundedness: 98, mrr: 0.91, latency: 195 },
  { domain: 'Legal Compliance', recall: 92, correctness: 86, groundedness: 97, mrr: 0.85, latency: 220 },
  { domain: 'Finance', recall: 95, correctness: 91, groundedness: 95, mrr: 0.89, latency: 175 },
  { domain: 'Healthcare Informatics', recall: 94, correctness: 88, groundedness: 96, mrr: 0.87, latency: 165 }
];

export const FAILURE_ANALYSIS_DATA: FailureAnalysis[] = [
  {
    id: 'fail-1',
    question: 'What are the exact compliance liabilities for pre-closing notification delays?',
    expectedSource: 'M_and_A_Agreement_Draft.docx',
    retrievedSource: 'No Context Retrieved',
    result: 'Model response initiated "Insufficient Context" safety block, correctly refusing to hypothesize liability limits without specific section data.',
    category: 'No Context Retrieved'
  },
  {
    id: 'fail-2',
    question: 'How do clinical records interact with remote diagnosis servers?',
    expectedSource: 'EHR_Standardization_Guide.txt',
    retrievedSource: 'Q2_Financial_Report.pdf',
    result: 'Retrieved cloud container optimization segment instead of clinical server specifications due to high keyword overlap on "servers".',
    category: 'Irrelevant Chunk'
  },
  {
    id: 'fail-3',
    question: 'What is the tax rate applied to municipal green energy bonds?',
    expectedSource: 'Climate_Action_Plan_2026.pdf',
    retrievedSource: 'Climate_Action_Plan_2026.pdf',
    result: 'Retrieved solar roofing requirements and general green bond funding, but failed to retrieve specific tax percentage, producing incomplete answer.',
    category: 'Incomplete Answer'
  }
];
