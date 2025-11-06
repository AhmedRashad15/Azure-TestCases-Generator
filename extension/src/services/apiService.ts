import * as SDK from "azure-devops-extension-sdk";

// API Service for calling the backend Flask API
// Configure the backend URL without rebuilding by either:
// - Adding ?api=https://your-api.azurewebsites.net to the extension URL, OR
// - Setting localStorage key 'TEST_GENIUS_API_URL' to your API base URL
// Fallback DEFAULT_API_BASE_URL is used only if the two mechanisms above are not provided
const DEFAULT_API_BASE_URL = ""; // e.g., "https://test-genius-api.azurewebsites.net"

let cachedApiBaseUrlPromise: Promise<string> | null = null;

async function getApiBaseUrl(): Promise<string> {
  const params = new URLSearchParams(window.location.search);
  const queryApi = params.get("api");
  const storedApi = window.localStorage.getItem("TEST_GENIUS_API_URL");
  let base = (queryApi || storedApi || DEFAULT_API_BASE_URL).trim();

  // If not supplied by query/localStorage/default, try to load from packaged config
  if (!base) {
    if (!cachedApiBaseUrlPromise) {
      cachedApiBaseUrlPromise = (async () => {
        try {
          // First try images/config.json (always addressable in extension)
          const configUrls = [
            "images/config.json", // packaged alongside other assets
            "config.json", // fallback next to index.html
          ];
          for (const url of configUrls) {
            try {
              const res = await fetch(url, { cache: "no-store" });
              if (res.ok) {
                const cfg = await res.json();
                if (cfg && typeof cfg.apiBaseUrl === "string" && cfg.apiBaseUrl.trim()) {
                  return cfg.apiBaseUrl.trim();
                }
              }
            } catch (_) {
              // continue
            }
          }
        } catch (_) {}
        return "";
      })();
    }
    base = await cachedApiBaseUrlPromise;
  }

  if (!base) {
    throw new Error(
      "API base URL not configured. Set localStorage 'TEST_GENIUS_API_URL', add ?api=https://<your-api>, or set images/config.json {\"apiBaseUrl\":\"https://<your-api>\"}."
    );
  }
  if (base.startsWith("http://")) {
    throw new Error("Backend must be HTTPS. HTTP is blocked by the browser (mixed content).");
  }
  return base.replace(/\/$/, "");
}

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
      const accessToken = await SDK.getAccessToken();
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
    relatedTestCases?: string,
    aiProvider: string = 'gemini'
  ): Promise<AnalysisResponse> {
    const headers = await this.getHeaders();

    // Send HTML content directly so backend can extract images
    // Backend will handle image extraction and processing
    const apiBase = await getApiBaseUrl();
    const response = await fetch(`${apiBase}/analyze_story`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        story_title: storyTitle,
        story_description: storyDescription, // Send HTML directly
        acceptance_criteria: acceptanceCriteria, // Send HTML directly
        related_test_cases: relatedTestCases,
        ai_provider: aiProvider,
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
    onProgress?: (progress: GenerateTestCasesResponse) => void,
    aiProvider: string = 'gemini',
    ambiguityAware: boolean = true
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
      ai_provider: aiProvider,
      ambiguity_aware: ambiguityAware,
    };

    // Use POST with streaming to support large payloads (images)
    return new Promise((resolve, reject) => {
      const allTestCases: any[] = [];

      getApiBaseUrl().then((apiBase) => fetch(`${apiBase}/generate_test_cases`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }))
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          const reader = response.body?.getReader();
          if (!reader) {
            throw new Error('Response body is not readable');
          }

          const decoder = new TextDecoder();

          function readStream() {
            reader!
              .read()
              .then(({ done, value }) => {
                if (done) {
                  resolve(allTestCases);
                  return;
                }

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                  if (line.startsWith('data: ')) {
                    try {
                      const data: GenerateTestCasesResponse = JSON.parse(
                        line.substring(6)
                      );

                      if (data.type === 'done') {
                        resolve(allTestCases);
                        return;
                      } else if (data.type === 'error') {
                        console.error(`Error generating ${data.case_type || 'test cases'}:`, data.error, data.message);
                        // Continue processing other case types - don't reject
                        if (onProgress) {
                          onProgress(data);
                        }
                      } else if (data.cases && Array.isArray(data.cases)) {
                        // Handle both empty and non-empty arrays
                        if (data.cases.length > 0) {
                          allTestCases.push(...data.cases);
                        }
                        if (onProgress) {
                          onProgress(data);
                        }
                      } else if (data.progress) {
                        // Handle progress messages even without cases
                        if (onProgress) {
                          onProgress(data);
                        }
                      }
                    } catch (error) {
                      console.error('Error parsing SSE data:', error);
                    }
                  }
                }

                readStream();
              })
              .catch((error) => {
                reject(new Error('Failed to generate test cases: ' + error));
              });
          }

          readStream();
        })
        .catch((error) => {
          reject(new Error('Failed to generate test cases: ' + error));
        });
    });
  }
}

export default new ApiService();

