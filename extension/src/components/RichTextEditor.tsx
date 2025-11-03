import React, { useRef, useEffect, useState } from "react";

interface RichTextEditorProps {
  value: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
}

const RichTextEditor: React.FC<RichTextEditorProps> = ({
  value,
  onChange,
  placeholder = "",
  readOnly = false,
  className = "",
}) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const [content, setContent] = useState<string>(value);

  useEffect(() => {
    if (editorRef.current && value !== content) {
      // Preserve HTML content including images
      editorRef.current.innerHTML = value || "";
      setContent(value);
    }
  }, [value]);

  const handlePaste = async (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (readOnly) return;

    e.preventDefault();
    e.stopPropagation();
    const clipboardData = e.clipboardData;

    if (!editorRef.current) {
      console.error("RichTextEditor: editorRef.current is null");
      return;
    }

    console.log("RichTextEditor: Paste event detected", {
      items: clipboardData.items.length,
      types: Array.from(clipboardData.types)
    });

    // Ensure editor has focus
    editorRef.current.focus();

    // Check if clipboard contains image
    if (clipboardData.items && clipboardData.items.length > 0) {
      for (let i = 0; i < clipboardData.items.length; i++) {
        const item = clipboardData.items[i];
        
        // Check for image types
        console.log("RichTextEditor: Checking item", { 
          type: item.type, 
          kind: item.kind 
        });
        
        if (item.type.indexOf("image") !== -1 || item.kind === "file") {
          const blob = item.getAsFile();
          if (blob && blob.type.startsWith("image/")) {
            console.log("RichTextEditor: Image detected!", { 
              blobType: blob.type, 
              blobSize: blob.size 
            });
            
            const reader = new FileReader();
            reader.onload = (event) => {
              const imageDataUrl = event.target?.result as string;
              
              console.log("RichTextEditor: Image loaded, inserting...");
              
              if (!editorRef.current) {
                console.error("RichTextEditor: editorRef.current is null in reader.onload");
                return;
              }
              
              // Create img element
              const img = document.createElement("img");
              img.src = imageDataUrl;
              img.style.maxWidth = "100%";
              img.style.height = "auto";
              img.style.display = "block";
              img.style.margin = "10px 0";
              img.alt = "Pasted image";
              
              // Get or create selection
              const selection = window.getSelection();
              let range: Range | null = null;
              
              if (selection && selection.rangeCount > 0) {
                range = selection.getRangeAt(0);
                // Check if range is within our editor
                if (!editorRef.current.contains(range.commonAncestorContainer)) {
                  range = null;
                }
              }
              
              // If no valid range, create one at the end of editor
              if (!range) {
                range = document.createRange();
                if (editorRef.current.childNodes.length > 0) {
                  range.selectNodeContents(editorRef.current);
                  range.collapse(false); // Collapse to end
                } else {
                  range.setStart(editorRef.current, 0);
                  range.setEnd(editorRef.current, 0);
                }
              }
              
              // Insert image
              range.deleteContents();
              range.insertNode(img);
              
              // Add a line break after image for better UX
              const br = document.createElement("br");
              range.setStartAfter(img);
              range.insertNode(br);
              
              // Move cursor after the line break
              range.setStartAfter(br);
              range.collapse(true);
              
              if (selection) {
                selection.removeAllRanges();
                selection.addRange(range);
              }
              
              // Update value with HTML content
              const newContent = editorRef.current.innerHTML;
              setContent(newContent);
              if (onChange) {
                onChange(newContent);
              }
            };
            
            reader.onerror = () => {
              console.error("Error reading image file");
            };
            
            reader.readAsDataURL(blob);
            return; // Exit early since we found an image
          }
        }
      }
    }

    // Fallback: paste as plain text or HTML if no image
    const htmlData = clipboardData.getData("text/html");
    const textData = clipboardData.getData("text/plain");
    
    if (htmlData && editorRef.current) {
      // Paste HTML content (but sanitize images - we already handled them above)
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = htmlData;
      
      // Remove any img tags from HTML paste (we want to handle images separately)
      const images = tempDiv.querySelectorAll("img");
      images.forEach(img => img.remove());
      
      const selection = window.getSelection();
      let range: Range | null = null;
      
      if (selection && selection.rangeCount > 0) {
        range = selection.getRangeAt(0);
        if (!editorRef.current.contains(range.commonAncestorContainer)) {
          range = null;
        }
      }
      
      if (!range) {
        range = document.createRange();
        if (editorRef.current.childNodes.length > 0) {
          range.selectNodeContents(editorRef.current);
          range.collapse(false);
        } else {
          range.setStart(editorRef.current, 0);
          range.setEnd(editorRef.current, 0);
        }
      }
      
      range.deleteContents();
      while (tempDiv.firstChild) {
        range.insertNode(tempDiv.firstChild);
        range.setStartAfter(range.endContainer.lastChild || range.endContainer);
      }
      range.collapse(false);
      
      if (selection) {
        selection.removeAllRanges();
        selection.addRange(range);
      }
    } else if (textData && editorRef.current) {
      // Paste as plain text
      const selection = window.getSelection();
      let range: Range | null = null;
      
      if (selection && selection.rangeCount > 0) {
        range = selection.getRangeAt(0);
        if (!editorRef.current.contains(range.commonAncestorContainer)) {
          range = null;
        }
      }
      
      if (!range) {
        range = document.createRange();
        if (editorRef.current.childNodes.length > 0) {
          range.selectNodeContents(editorRef.current);
          range.collapse(false);
        } else {
          range.setStart(editorRef.current, 0);
          range.setEnd(editorRef.current, 0);
        }
      }
      
      range.deleteContents();
      const textNode = document.createTextNode(textData);
      range.insertNode(textNode);
      range.setStartAfter(textNode);
      range.collapse(true);
      
      if (selection) {
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
    
    // Update value after paste
    if (editorRef.current) {
      const newContent = editorRef.current.innerHTML;
      setContent(newContent);
      if (onChange) {
        onChange(newContent);
      }
    }
  };

  const handleInput = () => {
    if (editorRef.current && !readOnly) {
      const newContent = editorRef.current.innerHTML;
      setContent(newContent);
      if (onChange) {
        onChange(newContent);
      }
    }
  };

  return (
    <div
      ref={editorRef}
      contentEditable={!readOnly}
      onPaste={handlePaste}
      onInput={handleInput}
      onFocus={(e) => {
        // Ensure cursor is positioned when focused
        if (editorRef.current && !readOnly) {
          const selection = window.getSelection();
          if (selection && editorRef.current.childNodes.length > 0) {
            const range = document.createRange();
            range.selectNodeContents(editorRef.current);
            range.collapse(false);
            selection.removeAllRanges();
            selection.addRange(range);
          }
        }
      }}
      className={`rich-text-editor ${className} ${readOnly ? "read-only" : ""}`}
      style={{
        minHeight: "120px",
        padding: "8px",
        border: "1px solid #dee2e6",
        borderRadius: "8px",
        outline: "none",
        backgroundColor: readOnly ? "#f8f9fa" : "#ffffff",
        cursor: readOnly ? "default" : "text",
        overflowWrap: "break-word",
        wordWrap: "break-word",
      }}
      data-placeholder={placeholder}
      suppressContentEditableWarning={true}
    />
  );
};

export default RichTextEditor;

