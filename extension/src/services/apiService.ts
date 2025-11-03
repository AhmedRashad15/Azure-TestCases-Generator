// API Service for calling the backend Flask API
// IMPORTANT: Replace this URL with your deployed backend API URL
// API Base URL - Update this after Azure deployment
// For now: local testing
// After Azure deployment: change to your Azure URL (e.g., "https://test-genius-api.azurewebsites.net")
const API_BASE_URL = process.env.REACT_APP_API_URL || "http://192.168.1.105:5000";

export interface AnalysisResponse {
  analysis: string;
}

export interface GenerateTestCasesResponse {
  type: string;
  cases?: any[];
  progress?: string;
  message?: string;
}

class ApiService {
  private extractTextFromHtml(html: string): string {
    // Create a temporary div to parse HTML
    const div = document.createElement("div");
    div.innerHTML = html;
    
    // Replace images with text description
    const images = div.querySelectorAll("img");
    images.forEach((img) => {
      const alt = img.getAttribute("alt") || "image";
      const textNode = document.createTextNode(`[Image: ${alt}]`);
      img.parentNode?.replaceChild(textNode, img);
    });
    
    // Get text content
    return div.textContent || div.innerText || "";
  }

  private async getHeaders(): Promise<HeadersInit> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };

    // If running in Azure DevOps extension, add token
    try {
      const SDK = await import("azure-devops-extension-sdk");
      const accessToken = await SDK.default.getAccessToken();
      if (accessToken) {
        headers["Authorization"] = `Bearer ${accessToken}`;
      }
    } catch (error) {
      console.warn("Could not get Azure DevOps token, using API without auth");
    }

    return headers;
  }

  async analyzeStory(
    storyTitle: string,
    storyDescription: string,
    acceptanceCriteria: string,
    relatedTestCases?: string
  ): Promise<AnalysisResponse> {
    const headers = await this.getHeaders();

    // Send HTML content directly so backend can extract images
    // Backend will handle image extraction and processing
    const response = await fetch(`${API_BASE_URL}/analyze_story`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        story_title: storyTitle,
        story_description: storyDescription, // Send HTML directly
        acceptance_criteria: acceptanceCriteria, // Send HTML directly
        related_test_cases: relatedTestCases,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  async generateTestCases(
    storyTitle: string,
    storyDescription: string,
    acceptanceCriteria: string,
    dataDictionary: string,
    relatedStories: any[],
    onProgress?: (progress: GenerateTestCasesResponse) => void
  ): Promise<any[]> {
    const headers = await this.getHeaders();

    // Send HTML content directly so backend can extract images
    // Backend will handle image extraction and processing
    const payload = {
      story_title: storyTitle,
      story_description: storyDescription, // Send HTML directly
      acceptance_criteria: acceptanceCriteria, // Send HTML directly
      data_dictionary: dataDictionary, // Send HTML directly
      related_stories: relatedStories,
    };

    // Use EventSource for streaming if backend supports it
    // Otherwise use regular fetch
    return new Promise((resolve, reject) => {
      const eventSource = new EventSource(
        `${API_BASE_URL}/generate_test_cases?payload=${encodeURIComponent(JSON.stringify(payload))}`
      );

      const allTestCases: any[] = [];

      eventSource.onmessage = (event) => {
        try {
          const data: GenerateTestCasesResponse = JSON.parse(event.data);

          if (data.type === "done") {
            eventSource.close();
            resolve(allTestCases);
          } else if (data.cases) {
            allTestCases.push(...data.cases);
            if (onProgress) {
              onProgress(data);
            }
          }
        } catch (error) {
          console.error("Error parsing SSE message:", error);
        }
      };

      eventSource.onerror = (error) => {
        eventSource.close();
        reject(new Error("Failed to generate test cases: " + error));
      };
    });
  }
}

export default new ApiService();

