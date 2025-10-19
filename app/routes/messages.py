"""
Messages routes
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import supabase_admin
from app.middleware.auth import get_current_user
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/messages")


class MessageCreate(BaseModel):
    recipient_id: str
    content: str
    property_id: Optional[str] = None
    application_id: Optional[str] = None


@router.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """
    Get user's conversations with last message
    """
    try:
        user_id = current_user["id"]
        
        # Fetch all messages where user is sender or recipient
        messages_response = supabase_admin.table("messages").select(
            "*, sender:users!sender_id(id, full_name, avatar_url, user_type), recipient:users!recipient_id(id, full_name, avatar_url, user_type)"
        ).or_(f"sender_id.eq.{user_id},recipient_id.eq.{user_id}").order("timestamp", desc=True).execute()
        
        # Group by conversation partner
        conversations = {}
        for msg in messages_response.data:
            # Determine conversation partner
            if msg["sender_id"] == user_id:
                partner = msg.get("recipient")
                partner_id = msg["recipient_id"]
            else:
                partner = msg.get("sender")
                partner_id = msg["sender_id"]
            
            # Only keep the latest message per conversation
            if partner_id not in conversations:
                conversations[partner_id] = {
                    "user": {
                        "id": partner["id"],
                        "name": partner.get("full_name"),
                        "avatar_url": partner.get("avatar_url"),
                        "user_type": partner.get("user_type")
                    },
                    "last_message": {
                        "content": msg["content"],
                        "timestamp": msg["timestamp"],
                        "read": msg["read"]
                    },
                    "unread_count": 0
                }
        
        # Count unread messages for each conversation
        for partner_id in conversations.keys():
            unread_response = supabase_admin.table("messages").select("id", count="exact").eq(
                "sender_id", partner_id
            ).eq("recipient_id", user_id).eq("read", False).execute()
            
            conversations[partner_id]["unread_count"] = unread_response.count if hasattr(unread_response, 'count') else 0
        
        return {
            "success": True,
            "conversations": list(conversations.values())
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {str(e)}"
        )


@router.get("/{user_id}")
async def get_messages(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get messages with specific user
    """
    try:
        current_user_id = current_user["id"]
        
        # Fetch messages between current user and specified user
        response = supabase_admin.table("messages").select(
            "*, sender:users!sender_id(id, full_name, avatar_url), recipient:users!recipient_id(id, full_name, avatar_url)"
        ).or_(
            f"and(sender_id.eq.{current_user_id},recipient_id.eq.{user_id}),and(sender_id.eq.{user_id},recipient_id.eq.{current_user_id})"
        ).order("timestamp", desc=False).execute()
        
        # Mark messages as read (where current user is recipient)
        supabase_admin.table("messages").update({
            "read": True,
            "read_at": datetime.now().isoformat()
        }).eq("sender_id", user_id).eq("recipient_id", current_user_id).eq("read", False).execute()
        
        return {
            "success": True,
            "messages": response.data
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch messages: {str(e)}"
        )


@router.post("/")
async def send_message(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a message to another user
    """
    try:
        sender_id = current_user["id"]
        
        # Verify recipient exists
        recipient_check = supabase_admin.table("users").select("id").eq(
            "id", message_data.recipient_id
        ).single().execute()
        
        if not recipient_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient not found"
            )
        
        # Create message
        msg_dict = {
            "sender_id": sender_id,
            "recipient_id": message_data.recipient_id,
            "content": message_data.content,
            "property_id": message_data.property_id,
            "application_id": message_data.application_id,
            "message_type": "text",
            "read": False,
            "attachments": []
        }
        
        response = supabase_admin.table("messages").insert(msg_dict).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to send message"
            )
        
        # TODO: Send real-time notification to recipient
        # TODO: Create notification record
        
        return {
            "success": True,
            "message": response.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send message: {str(e)}"
        )
