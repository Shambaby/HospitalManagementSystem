#include<bits/stdc++.h>
#include<iostream>
#include<vector>
using namespace std;
class BookingSystem{
    private:
    vector<Room> rooms;

    public:
        void addRoom(Room r){
            rooms.push_back(r);
        }
        //delete room
        bool bookRoom(string roomName){
            for(auto& r : rooms){
                if(r.getName() == roomName) {
                    return r.book();
                }
                else return false;
            }
        }
        
};
class Room{
    private:
        string name;
        bool isBooked;

    public:
        Room(string n){
            name=n;
            isBooked=false;
        }

        bool isAvailable(){
            return !isBooked;
        }

        bool book(){
            if(isBooked) return false;
            isBooked = true;
            return true;
        }

        string getName(){
            return name;
        }
};