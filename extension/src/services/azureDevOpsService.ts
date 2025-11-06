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
  /**
   * Extract organization URL and project name
   * Azure DevOps extensions receive project info via URL parameters or referrer
   */
  private async getOrgUrlAndProject(): Promise<{ orgUrl: string; projectName: string }> {
    let orgUrl = "";
    let projectName = "";
    
    // Step 0: Use Azure DevOps SDK to get org URL and project (works even in iframe)
    try {
      const host = SDK.getHost();
      const hostUri = (host as any).uri || (host as any).url || "";
      if (hostUri && !hostUri.includes("vsassets") && !hostUri.includes("gallerycdn")) {
        if (hostUri.includes("visualstudio.com")) {
          const m = hostUri.match(/https?:\/\/[^/]+\.visualstudio\.com/);
          if (m) orgUrl = m[0];
        } else if (hostUri.includes("dev.azure.com")) {
          const m = hostUri.match(/https?:\/\/dev\.azure\.com\/[^/]+/);
          if (m) orgUrl = m[0];
        }
      }
      // Try ProjectPageService for project name
      try {
        const projectService = await (SDK as any).getService((SDK as any).CommonServiceIds?.ProjectPageService || "ms.vss-tfs-web.tfs-page-data-service");
        if (projectService && projectService.getProject) {
          const prj = await projectService.getProject();
          if (prj && prj.name) {
            projectName = prj.name;
          }
        }
      } catch (e) {
        // ignore and continue with other strategies
      }
    } catch (e) {
      // ignore and continue
    }
    
    // Step 1: Extract from document.referrer (most reliable)
    if (typeof document !== 'undefined' && document.referrer) {
      const referrer = document.referrer;
      console.log("Document referrer:", referrer);
      
      // Extract org URL
      if (referrer.includes('visualstudio.com')) {
        const match = referrer.match(/https?:\/\/[^\/]+\.visualstudio\.com/);
        if (match) {
          orgUrl = match[0];
          console.log("Extracted org URL from referrer:", orgUrl);
          
          // Extract project name from referrer URL path
          // Format: https://org.visualstudio.com/ProjectName/...
          try {
            const urlObj = new URL(referrer);
            const pathParts = urlObj.pathname.split('/').filter(p => p && !p.startsWith('_'));
            
            // Skip common Azure DevOps paths
            const skipPaths = ['extensions', '_apps', '_work', '_admin', '_settings'];
            const orgName = orgUrl.match(/https?:\/\/([^\/]+)\.visualstudio\.com/)?.[1]?.toLowerCase() || "";
            
            for (const part of pathParts) {
              const partLower = part.toLowerCase();
              if (!skipPaths.includes(partLower) && partLower !== orgName) {
                projectName = decodeURIComponent(part);
                console.log("Extracted project name from referrer:", projectName);
                break;
              }
            }
          } catch (e) {
            console.log("Error parsing referrer URL:", e);
          }
        }
      } else if (referrer.includes('dev.azure.com')) {
        const match = referrer.match(/https?:\/\/dev\.azure\.com\/[^\/]+/);
        if (match) {
          orgUrl = match[0];
          console.log("Extracted org URL from referrer:", orgUrl);
          
          // Extract project name from dev.azure.com URL
          // Format: https://dev.azure.com/org/ProjectName/...
          try {
            const urlObj = new URL(referrer);
            const pathParts = urlObj.pathname.split('/').filter(p => p && !p.startsWith('_'));
            
            const skipPaths = ['extensions', '_apps', '_work', '_admin', '_settings'];
            const orgName = orgUrl.match(/https?:\/\/dev\.azure\.com\/([^\/]+)/)?.[1]?.toLowerCase() || "";
            
            // First part after org is usually the project name
            for (const part of pathParts) {
              const partLower = part.toLowerCase();
              if (!skipPaths.includes(partLower) && partLower !== orgName) {
                projectName = decodeURIComponent(part);
                console.log("Extracted project name from referrer:", projectName);
                break;
              }
            }
          } catch (e) {
            console.log("Error parsing referrer URL:", e);
          }
        }
      }
    }
    
    // Step 2: Try URL parameters (Azure DevOps may pass project as query param)
    if (!projectName && typeof window !== 'undefined' && window.location) {
      const urlParams = new URLSearchParams(window.location.search);
      const projectParam = urlParams.get("project") || urlParams.get("projectId");
      if (projectParam) {
        projectName = decodeURIComponent(projectParam);
        console.log("Got project name from URL parameter:", projectName);
      }
    }
    
    // Step 3: Fallback - use REST API if we have orgUrl but no projectName
    if (orgUrl && !projectName) {
      try {
        const accessToken = await SDK.getAccessToken();
        if (accessToken) {
          // Get all projects and try to match from referrer path
          const projectsUrl = `${orgUrl}/_apis/projects?api-version=7.1`;
          const response = await fetch(projectsUrl, {
            headers: {
              Authorization: `Bearer ${accessToken}`,
              "Content-Type": "application/json",
            },
          });
          
          if (response.ok) {
            const projectsData = await response.json();
            if (projectsData.value && projectsData.value.length > 0) {
              // Try to extract from referrer one more time with better parsing
              const referrer = document.referrer || "";
              if (referrer) {
                try {
                  const urlObj = new URL(referrer);
                  const pathParts = urlObj.pathname.split('/').filter(p => p && !p.startsWith('_'));
                  const skipPaths = ['extensions', '_apps', '_work', '_admin', '_settings'];
                  const orgName = orgUrl.match(/https?:\/\/([^\/]+)\.(?:visualstudio\.com|dev\.azure\.com\/[^\/]+)/)?.[1]?.toLowerCase() || "";
                  
                  for (const part of pathParts) {
                    const partLower = part.toLowerCase();
                    if (!skipPaths.includes(partLower) && partLower !== orgName) {
                      const candidate = decodeURIComponent(part);
                      // Check if this project exists
                      const found = projectsData.value.find((p: any) => 
                        p.name.toLowerCase() === candidate.toLowerCase()
                      );
                      if (found) {
                        projectName = found.name; // Use the exact name from API
                        console.log("Matched project from API:", projectName);
                        break;
                      }
                    }
                  }
                } catch (e) {
                  console.log("Error matching project:", e);
                }
              }
              
              // If still no project and only one exists, use it
              if (!projectName && projectsData.value.length === 1) {
                projectName = projectsData.value[0].name;
                console.log("Using single project from API:", projectName);
              }
            }
          }
        }
      } catch (e) {
        console.log("Could not get project name from REST API:", e);
      }
    }
    
    console.log("Final detected orgUrl:", orgUrl);
    console.log("Final detected projectName:", projectName);
    
    return { orgUrl, projectName };
  }

  async getWorkItem(workItemId: number): Promise<WorkItem> {
    try {
      // Get org URL and project name (async method)
      const { orgUrl, projectName } = await this.getOrgUrlAndProject();
      
      if (!orgUrl || !projectName) {
        throw new Error(`Unable to get organization URL or project name. orgUrl: ${orgUrl || 'missing'}, projectName: ${projectName || 'missing'}. Please access the extension from within a project context.`);
      }
      
      // Ensure orgUrl doesn't end with / and construct proper URL
      const baseUrl = orgUrl.endsWith('/') ? orgUrl.slice(0, -1) : orgUrl;

      const accessToken = await SDK.getAccessToken();
      
      if (!accessToken) {
        throw new Error("Unable to get access token");
      }
      
      // Use REST API directly - proper URL format
      const apiUrl = `${baseUrl}/${encodeURIComponent(projectName)}/_apis/wit/workitems/${workItemId}?$expand=all&api-version=7.1`;
      console.log("Fetching work item from:", apiUrl);
      console.log("Using access token:", accessToken ? "Present" : "Missing");
      
      const response = await fetch(apiUrl, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("API Error:", response.status, errorText);
        console.error("Request URL was:", apiUrl);
        throw new Error(`Failed to fetch work item: ${response.statusText} (${response.status})`);
      }

      const workItem = await response.json();
      const fields = workItem.fields;

      // Parse HTML descriptions
      const descriptionHtml = fields["System.Description"] || "";
      const acceptanceCriteriaHtml = fields["Microsoft.VSTS.Common.AcceptanceCriteria"] || "";

      // Convert Azure DevOps image URLs to base64 data URLs for display
      const description = await this.convertAzureDevOpsImagesToDataUrls(descriptionHtml, orgUrl, accessToken);
      const acceptance_criteria = await this.convertAzureDevOpsImagesToDataUrls(acceptanceCriteriaHtml, orgUrl, accessToken);

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
    // Get org URL and project name (async method)
    const { orgUrl, projectName } = await this.getOrgUrlAndProject();
    
    if (!orgUrl || !projectName) {
      throw new Error("Unable to get organization URL or project name");
    }
    
    const baseUrl = orgUrl.endsWith('/') ? orgUrl.slice(0, -1) : orgUrl;
    const accessToken = await SDK.getAccessToken();

    const response = await fetch(
      `${baseUrl}/${encodeURIComponent(projectName)}/_apis/wit/workitems/${workItemId}?$expand=all&api-version=7.1`,
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

  /**
   * Convert Azure DevOps image URLs (vstfs:// or attachment URLs) to base64 data URLs
   * This allows images from Azure DevOps work items to be displayed in our rich text editors
   */
  private async convertAzureDevOpsImagesToDataUrls(
    html: string,
    orgUrl: string,
    accessToken: string
  ): Promise<string> {
    if (!html) return html;

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const images = doc.querySelectorAll("img");

    for (const img of Array.from(images)) {
      const src = img.getAttribute("src");
      if (!src) continue;

      try {
        // Check if it's already a data URL
        if (src.startsWith("data:image")) {
          continue; // Already in the right format
        }

        // Handle Azure DevOps attachment URLs
        // Format 1: vstfs:///Attachments/... (needs conversion to REST API URL)
        // Format 2: https://.../_apis/wit/attachments/... (direct REST API URL)
        let imageUrl = src;

        // Convert vstfs:// URLs to REST API URLs
        if (src.startsWith("vstfs:///")) {
          // Extract attachment ID from vstfs URL
          // vstfs:///Attachments/Attachments/[attachment-id]/filename
          const match = src.match(/\/Attachments\/([^\/]+)/);
          if (match && match[1]) {
            const attachmentId = match[1];
            imageUrl = `${orgUrl}/_apis/wit/attachments/${attachmentId}?fileName=${encodeURIComponent(
              img.getAttribute("alt") || "image.png"
            )}`;
          } else {
            console.warn("Could not parse vstfs URL:", src);
            continue;
          }
        }

        // If it's a relative URL, make it absolute
        if (imageUrl.startsWith("/")) {
          imageUrl = `${orgUrl}${imageUrl}`;
        }

        // Only process Azure DevOps URLs (skip external URLs)
        if (!imageUrl.includes("/_apis/") && !imageUrl.includes("visualstudio.com") && !imageUrl.includes("dev.azure.com")) {
          console.log("Skipping external image URL:", imageUrl);
          continue;
        }

        // Fetch the image and convert to base64
        const imageResponse = await fetch(imageUrl, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        });

        if (imageResponse.ok) {
          const blob = await imageResponse.blob();
          const reader = new FileReader();
          
          await new Promise<void>((resolve, reject) => {
            reader.onloadend = () => {
              const base64data = reader.result as string;
              img.setAttribute("src", base64data);
              resolve();
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
        } else {
          console.warn("Failed to fetch Azure DevOps image:", imageUrl, imageResponse.status);
          // Keep original URL as fallback
        }
      } catch (error) {
        console.error("Error converting Azure DevOps image to data URL:", error);
        // Keep original URL as fallback
      }
    }

    return doc.documentElement.innerHTML;
  }

  async uploadTestCases(
    testCases: TestCase[],
    testPlanId: number,
    testSuiteId: number
  ): Promise<void> {
    // Get org URL and project name (async method)
    const { orgUrl, projectName } = await this.getOrgUrlAndProject();
    
    if (!orgUrl || !projectName) {
      throw new Error("Unable to get organization URL or project name");
    }
    
    const baseUrl = orgUrl.endsWith('/') ? orgUrl.slice(0, -1) : orgUrl;
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
        `${baseUrl}/${encodeURIComponent(projectName)}/_apis/wit/workitems/$Test Case?api-version=7.1`,
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
      `${baseUrl}/${encodeURIComponent(projectName)}/_apis/testplan/Plans/${testPlanId}/Suites/${testSuiteId}/TestCases?api-version=7.1-preview.2`,
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

