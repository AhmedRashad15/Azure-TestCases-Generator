import * as SDK from "azure-devops-extension-sdk";

export interface WorkItem {
  id: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  related_stories?: RelatedStory[];
}

export interface RelatedStory {
  id: string;
  title: string;
  description: string;
  acceptance_criteria: string;
}

export interface TestCase {
  id?: string;
  title: string;
  priority: string;
  description: string;
  expectedResult: string;
}

class AzureDevOpsService {
  async getWorkItem(workItemId: number): Promise<WorkItem> {
    try {
      // Get organization URL and project from context
      const host = SDK.getHost();
      const orgUrl = (host as any).uri || (host as any).url || "";
      const project = (host as any).name || "";

      const accessToken = await SDK.getAccessToken();
      
      // Use REST API directly
      const response = await fetch(
        `${orgUrl}${project}/_apis/wit/workitems/${workItemId}?$expand=all&api-version=7.1`,
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch work item: ${response.statusText}`);
      }

      const workItem = await response.json();
      const fields = workItem.fields;

      // Parse HTML descriptions
      const descriptionHtml = fields["System.Description"] || "";
      const acceptanceCriteriaHtml = fields["Microsoft.VSTS.Common.AcceptanceCriteria"] || "";

      // Keep HTML for description and acceptance criteria to preserve images
      const description = descriptionHtml || "";
      const acceptance_criteria = acceptanceCriteriaHtml || "";

      // Fetch related stories
      const related_stories: RelatedStory[] = [];
      if (workItem.relations) {
        for (const rel of workItem.relations) {
          if (
            rel.rel === "System.LinkTypes.Related" ||
            rel.rel === "System.LinkTypes.Hierarchy-Forward" ||
            rel.rel === "System.LinkTypes.Hierarchy-Reverse"
          ) {
            const relatedId = rel.url.split("/").pop();
            if (relatedId) {
              try {
                const relatedItem = await this.getRelatedWorkItem(parseInt(relatedId));
                if (relatedItem && relatedItem.fields["System.WorkItemType"] === "User Story") {
                  related_stories.push({
                    id: relatedId,
                    title: relatedItem.fields["System.Title"] || "",
                    description: this.htmlToText(relatedItem.fields["System.Description"] || ""),
                    acceptance_criteria: this.htmlToText(
                      relatedItem.fields["Microsoft.VSTS.Common.AcceptanceCriteria"] || ""
                    ),
                  });
                }
              } catch (error) {
                console.warn(`Failed to fetch related story ${relatedId}:`, error);
              }
            }
          }
        }
      }

      return {
        id: workItem.id ? workItem.id.toString() : workItemId.toString(),
        title: fields["System.Title"] || "",
        description,
        acceptance_criteria,
        related_stories,
      };
    } catch (error) {
      console.error("Error fetching work item:", error);
      throw error;
    }
  }

  private async getRelatedWorkItem(workItemId: number): Promise<any> {
    const host = SDK.getHost();
    const orgUrl = (host as any).uri || (host as any).url || "";
    const project = (host as any).name || "";
    const accessToken = await SDK.getAccessToken();

    const response = await fetch(
      `${orgUrl}${project}/_apis/wit/workitems/${workItemId}?$expand=all&api-version=7.1`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch related work item: ${response.statusText}`);
    }

    return await response.json();
  }

  private htmlToText(html: string): string {
    // Simple HTML to text conversion
    const div = document.createElement("div");
    div.innerHTML = html;
    return div.textContent || div.innerText || "";
  }

  async uploadTestCases(
    testCases: TestCase[],
    testPlanId: number,
    testSuiteId: number
  ): Promise<void> {
    const host = SDK.getHost();
    const orgUrl = (host as any).uri || (host as any).url || "";
    const project = (host as any).name || "";
    const accessToken = await SDK.getAccessToken();

    // First, create test case work items
    const testCaseIds: number[] = [];

    for (const testCase of testCases) {
      const workItemPatch = [
        {
          op: "add",
          path: "/fields/System.Title",
          value: testCase.title,
        },
        {
          op: "add",
          path: "/fields/Microsoft.VSTS.Common.Priority",
          value: this.priorityToNumber(testCase.priority),
        },
      ];

      // Format test steps
      if (testCase.description || testCase.expectedResult) {
        const stepsXml = this.formatTestSteps(testCase.description, testCase.expectedResult);
        if (stepsXml) {
          workItemPatch.push({
            op: "add",
            path: "/fields/Microsoft.VSTS.TCM.Steps",
            value: stepsXml,
          });
        }
      }

      // Create test case work item
      const createResponse = await fetch(
        `${orgUrl}${project}/_apis/wit/workitems/$Test Case?api-version=7.1`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json-patch+json",
          },
          body: JSON.stringify(workItemPatch),
        }
      );

      if (!createResponse.ok) {
        throw new Error(`Failed to create test case: ${createResponse.statusText}`);
      }

      const createdItem = await createResponse.json();
      testCaseIds.push(createdItem.id);
    }

    // Add test cases to test suite
    const addToSuiteResponse = await fetch(
      `${orgUrl}${project}/_apis/testplan/Plans/${testPlanId}/Suites/${testSuiteId}/TestCases?api-version=7.1-preview.2`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          suiteTestCases: testCaseIds.map((id) => ({
            workItem: { id },
          })),
        }),
      }
    );

    if (!addToSuiteResponse.ok) {
      throw new Error(`Failed to add test cases to suite: ${addToSuiteResponse.statusText}`);
    }
  }

  private priorityToNumber(priority: string): number {
    const priorityMap: { [key: string]: number } = {
      critical: 1,
      high: 2,
      medium: 3,
      low: 4,
    };
    return priorityMap[priority.toLowerCase()] || 3;
  }

  private formatTestSteps(description: string, expectedResult: string): string {
    const steps = description.split("\n").filter((s) => s.trim());
    if (steps.length === 0 && !expectedResult) {
      return "";
    }

    const stepParts: string[] = [];
    steps.forEach((step, index) => {
      const cleanedStep = step.replace(/^\d+\.\s*/, "").trim();
      const isLastStep = index === steps.length - 1;
      const expected = isLastStep && expectedResult ? this.escapeXml(expectedResult) : "";

      stepParts.push(
        `<step id='${index + 1}' type='ActionStep'>
          <parameterizedString isformatted='true'>${this.escapeXml(cleanedStep)}</parameterizedString>
          <parameterizedString isformatted='true'>${expected}</parameterizedString>
        </step>`
      );
    });

    return `<steps id='0' last='${steps.length}'>${stepParts.join("")}</steps>`;
  }

  private escapeXml(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");
  }
}

export default new AzureDevOpsService();

